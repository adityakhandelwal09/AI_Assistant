from io import BytesIO
import html
import re
from bs4 import BeautifulSoup
from googleapiclient.http import MediaIoBaseDownload
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config.auth import get_google_service
from memory.vector_store import add_chunks


service = get_google_service("drive", "v3")
docs_service = get_google_service("docs", "v1")
slides_service = get_google_service("slides", "v1")

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_DOCUMENT_MIME_TYPE = "application/vnd.google-apps.document"
GOOGLE_PRESENTATION_MIME_TYPE = "application/vnd.google-apps.presentation"
GOOGLE_EXPORT_MIME_TYPES = {
    GOOGLE_DOCUMENT_MIME_TYPE: "text/plain",
    GOOGLE_PRESENTATION_MIME_TYPE: "text/plain",
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
}
DIRECT_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "application/json",
    "application/xml",
    "application/rtf",
    "application/x-yaml",
    "application/yaml",
}
MAX_FILE_BYTES = 20 * 1024 * 1024


class UnsupportedDriveFile(Exception):
    """Raised when a file cannot be converted into useful text."""


def normalize_drive_text(text):
    #normalizes extracted text while preserving paragraphs and table-like line breaks
    if not text:
        return ""

    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def list_drive_files(max_files=None, include_shared=False):
    #retrieves personal files by default and can optionally include shared files
    files = []
    page_token = None

    while True:
        #requests ownership metadata so shared files can be filtered before extraction.
        response = service.files().list(
            q=f"trashed = false and mimeType != '{FOLDER_MIME_TYPE}'",
            spaces="drive",
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=1000,
            pageToken=page_token,
            fields=(
                "nextPageToken, files(id, name, mimeType, description, createdTime, "
                "modifiedTime, webViewLink, parents, size, ownedByMe)"
            ),
        ).execute()
        page_files = response.get("files", [])
        if not include_shared:
            page_files = [file for file in page_files if file.get("ownedByMe")]
        files.extend(page_files)
        if max_files is not None and len(files) >= max_files:
            return files[:max_files]

        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_drive_bytes(file_id, mime_type, is_google_file):
    #download a file or export a Google-native file to get the raw content
    if is_google_file:
        export_mime_type = GOOGLE_EXPORT_MIME_TYPES.get(mime_type)
        if not export_mime_type:
            raise UnsupportedDriveFile(f"Unsupported Google file type: {mime_type}")
        request = service.files().export_media(fileId=file_id, mimeType=export_mime_type) #builds the actual REQUEST object that will fetch the exported content that you will convert to a real format later
    else:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True) #requests the file content normally, no conversion needed

    #pulls the file's content chunk-by-chunk into memory and returns the complete raw bytes to be processed by whichever function calls it
    output = BytesIO()
    downloader = MediaIoBaseDownload(output, request)
    complete = False
    while not complete:
        _, complete = downloader.next_chunk()
    return output.getvalue()


def extract_spreadsheet_text(file_bytes):
    #extract spreadsheet text while preserving sheet names, column headers, and row meaning
    try:
        from openpyxl import load_workbook
    except ImportError as error:
        raise UnsupportedDriveFile("XLSX extraction requires openpyxl.") from error

    workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    sections = []
    for worksheet in workbook.worksheets:
        rows = []
        for row in worksheet.iter_rows(values_only=True):
            values = ["" if value is None else normalize_drive_text(str(value)) for value in row]
            if any(values):
                rows.append(values)
        if not rows:
            continue
        if len(rows) == 1:
            values = [value for value in rows[0] if value]
            sections.append(f"Sheet: {worksheet.title}\n" + " | ".join(values))
            continue

        headers = rows[0]
        data_rows = rows[1:]
        column_values = [[] for _ in range(max(len(headers), max(map(len, data_rows))))]
        for row in data_rows:
            for column_index, value in enumerate(row):
                if value:
                    column_values[column_index].append(value)

        formatted_columns = []
        for column_index, values in enumerate(column_values):
            if not values:
                continue
            header = headers[column_index] if column_index < len(headers) else ""
            label = header or f"Column {column_index + 1}"
            formatted_columns.append(f"{label}: {', '.join(values)}")

        if formatted_columns:
            sections.append(f"Sheet: {worksheet.title}\n" + "\n".join(formatted_columns))
    return "\n\n".join(sections)


def extract_pdf_text(file_bytes):
    #extract readable text from a text-based PDF
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise UnsupportedDriveFile("PDF extraction requires pypdf.") from error

    reader = PdfReader(BytesIO(file_bytes))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_docx_text(file_bytes):
    #extract paragraphs and tables from a Word document
    try:
        from docx import Document
    except ImportError as error:
        raise UnsupportedDriveFile("Word extraction requires python-docx.") from error

    document = Document(BytesIO(file_bytes))
    sections = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                sections.append(" | ".join(values))
    return "\n".join(sections)


def extract_structural_elements_text(elements):
    #recursively extracts readable text from paragraphs, tables, and table-of-contents elements
    text_parts = []

    for element in elements:
        paragraph = element.get("paragraph")
        if paragraph:
            for paragraph_element in paragraph.get("elements", []):
                text_parts.append(
                    paragraph_element.get("textRun", {}).get("content", "")
                )

        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    text_parts.append(
                        extract_structural_elements_text(cell.get("content", []))
                    )

        table_of_contents = element.get("tableOfContents")
        if table_of_contents:
            text_parts.append(
                extract_structural_elements_text(table_of_contents.get("content", []))
            )

    return "".join(text_parts)


def iter_document_tabs(tabs):
    #yields every top-level and nested Google Docs tab without flattening the hierarchy
    for tab in tabs:
        yield tab
        yield from iter_document_tabs(tab.get("childTabs", []))


def extract_google_document_sections(file_id):
    #returns one independently chunked text section for each Google Docs tab
    document = docs_service.documents().get(
        documentId=file_id,
        includeTabsContent=True,
    ).execute()

    sections = []
    for tab in iter_document_tabs(document.get("tabs", [])):
        properties = tab.get("tabProperties", {})
        body = tab.get("documentTab", {}).get("body", {})
        text = normalize_drive_text(
            extract_structural_elements_text(body.get("content", []))
        )
        if text:
            sections.append(
                {
                    "section_id": properties.get("tabId", "tab"),
                    "section_title": properties.get("title", "Untitled tab"),
                    "text": text,
                }
            )

    return sections


def extract_slides_text_elements(text_elements):
    #joins the text runs from one Slides shape or table cell.
    return "".join(
        element.get("textRun", {}).get("content", "")
        for element in text_elements
    )


def extract_slide_table_text(table):
    #extracts visible text from every cell in a Slides table.
    rows = []
    for row in table.get("tableRows", []):
        values = []
        for cell in row.get("tableCells", []):
            value = normalize_drive_text(
                extract_slides_text_elements(cell.get("text", {}).get("textElements", []))
            )
            if value:
                values.append(value)
        if values:
            rows.append(" | ".join(values))
    return "\n".join(rows)


def extract_slide_page_elements(page_elements):
    #collects text and layout positions from shapes, tables, and grouped elements.
    extracted_elements = []
    for page_element in page_elements:
        transform = page_element.get("transform", {})
        position = (
            transform.get("translateY", 0),
            transform.get("translateX", 0),
        )
        shape = page_element.get("shape")
        if shape:
            text = normalize_drive_text(
                extract_slides_text_elements(shape.get("text", {}).get("textElements", []))
            )
            if text:
                extracted_elements.append(
                    {
                        "text": text,
                        "placeholder_type": shape.get("placeholder", {}).get("type", ""),
                        "position": position,
                    }
                )

        table = page_element.get("table")
        if table:
            text = normalize_drive_text(extract_slide_table_text(table))
            if text:
                extracted_elements.append(
                    {"text": text, "placeholder_type": "", "position": position}
                )

        group = page_element.get("elementGroup", {})
        if group:
            extracted_elements.extend(
                extract_slide_page_elements(group.get("children", []))
            )

    return extracted_elements


def extract_google_presentation_sections(file_id):
    #returns one independently chunked section per slide with its title before its body text.
    presentation = slides_service.presentations().get(
        presentationId=file_id,
    ).execute()

    sections = []
    for slide_number, slide in enumerate(presentation.get("slides", []), start=1):
        elements = extract_slide_page_elements(slide.get("pageElements", []))
        title_elements = [
            element["text"]
            for element in elements
            if element["placeholder_type"] in {"TITLE", "CENTERED_TITLE"}
        ]
        body_elements = [
            element for element in elements
            if element["placeholder_type"] not in {"TITLE", "CENTERED_TITLE"}
        ]
        body_elements.sort(key=lambda element: element["position"])

        title = " ".join(title_elements)
        lines = [f"Slide {slide_number}"]
        if title:
            lines.append(f"Title: {title}")
        lines.extend(element["text"] for element in body_elements)
        text = "\n".join(lines)

        if len(lines) > 1:
            sections.append(
                {
                    "section_id": slide.get("objectId", f"slide_{slide_number}"),
                    "section_title": title or f"Slide {slide_number}",
                    "section_label": "Slide title",
                    "text": text,
                }
            )

    return sections


def extract_file_text(file):
    #download and extract text according to the file's MIME type
    file_id = file["id"]
    mime_type = file.get("mimeType", "")
    is_google_file = mime_type.startswith("application/vnd.google-apps.")
    file_size = int(file.get("size", 0) or 0)
    if file_size > MAX_FILE_BYTES:
        raise UnsupportedDriveFile(f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")

    file_bytes = download_drive_bytes(file_id, mime_type, is_google_file)
    #applies the size limit after export because Google-native files lack size metadata.
    if len(file_bytes) > MAX_FILE_BYTES:
        raise UnsupportedDriveFile(f"Extracted file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
    if mime_type in GOOGLE_EXPORT_MIME_TYPES:
        if mime_type == "application/vnd.google-apps.spreadsheet":
            return normalize_drive_text(extract_spreadsheet_text(file_bytes))
        return normalize_drive_text(file_bytes.decode("utf-8", errors="replace"))

    if mime_type in DIRECT_TEXT_MIME_TYPES or mime_type.startswith("text/"):
        text = file_bytes.decode("utf-8", errors="replace")
        if mime_type == "text/html":
            text = BeautifulSoup(text, "html.parser").get_text("\n")
        return normalize_drive_text(text)
    if mime_type == "application/pdf":
        return normalize_drive_text(extract_pdf_text(file_bytes))
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return normalize_drive_text(extract_docx_text(file_bytes))
    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return normalize_drive_text(extract_spreadsheet_text(file_bytes))

    raise UnsupportedDriveFile(f"Unsupported file type: {mime_type}")


def extract_file_sections(file):
    #returns separate sections so Google Docs tabs can never be combined into one chunk.
    if file.get("mimeType") == GOOGLE_DOCUMENT_MIME_TYPE:
        sections = extract_google_document_sections(file["id"])
        for section in sections:
            section["section_label"] = "Document tab"
        return sections
    if file.get("mimeType") == GOOGLE_PRESENTATION_MIME_TYPE:
        return extract_google_presentation_sections(file["id"])

    return [
        {
            "section_id": "document",
            "section_title": None,
            "section_label": None,
            "text": extract_file_text(file),
        }
    ]


def chunk_document_text(text, chunk_size=500, chunk_overlap=50):
    #splits long documents by headings and paragraphs before falling back to sentences.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=lambda value: len(re.findall(r"\S+", value)),
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def word_count(text):
    #counts words consistently with the document chunking limit.
    return len(re.findall(r"\S+", text))


def build_file_header(file, section_title=None, section_label=None):
    #creates factual file context shared by every chunk from the same document
    lines = [f"File: {file.get('name', 'Untitled file')}"]
    if file.get("mimeType"):
        lines.append(f"Type: {file['mimeType']}")
    if file.get("modifiedTime"):
        lines.append(f"Last modified: {file['modifiedTime']}")
    description = normalize_drive_text(file.get("description", ""))
    if description:
        lines.append(f"File description: {description}")
    if section_title:
        lines.append(f"{section_label or 'Section'}: {section_title}")
    return "\n".join(lines)


def create_file_chunks(
    file,
    file_text,
    section_id="document",
    section_title=None,
    section_label=None,
):
    #creates chunks for contextual retrieval from one extracted Drive file
    if not file_text:
        return []

    file_id = file["id"]
    header = build_file_header(file, section_title, section_label)
    chunks = []
    for chunk_index, document_chunk in enumerate(chunk_document_text(file_text)):
        #keeps every chunk understandable even when retrieved without its neighbors.
        display_text = f"{header}\n\n{document_chunk}"
        chunks.append(
            {
                "chunk_id": f"drive_{file_id}_{section_id}_{chunk_index}",
                "embedding_text": display_text,
                "display_text": display_text,
                "metadata": {
                    "thread_id": file_id,
                    "message_id": str(chunk_index),
                    "source": "drive",
                    "file_id": file_id,
                    "file_name": file.get("name", "Untitled file"),
                    "mime_type": file.get("mimeType", ""),
                    "modified_time": file.get("modifiedTime", ""),
                    "created_time": file.get("createdTime", ""),
                    "web_view_link": file.get("webViewLink", ""),
                    "parent_ids": ", ".join(file.get("parents", [])),
                    "section_id": section_id,
                    "section_title": section_title or "",
                    "section_label": section_label or "",
                },
            }
        )
    return chunks


def create_presentation_chunks(file, slide_sections, chunk_size=500):
    #packs complete consecutive slides together and only splits a slide that exceeds the limit.
    all_chunks = []
    active_sections = []
    active_word_count = 0

    def add_active_sections():
        #writes the current group as one chunk because its combined text fits the limit.
        if not active_sections:
            return
        first_section = active_sections[0]
        last_section = active_sections[-1]
        section_id = f"slides_{first_section['section_id']}_{last_section['section_id']}"
        all_chunks.extend(
            create_file_chunks(
                file,
                "\n\n".join(section["text"] for section in active_sections),
                section_id=section_id,
            )
        )

    for section in slide_sections:
        section_word_count = word_count(section["text"])
        if section_word_count > chunk_size:
            add_active_sections()
            active_sections = []
            active_word_count = 0
            all_chunks.extend(
                create_file_chunks(
                    file,
                    section["text"],
                    section_id=section["section_id"],
                    section_title=section["section_title"],
                    section_label=section["section_label"],
                )
            )
            continue

        if active_sections and active_word_count + section_word_count > chunk_size:
            add_active_sections()
            active_sections = []
            active_word_count = 0

        active_sections.append(section)
        active_word_count += section_word_count

    add_active_sections()
    return all_chunks


def ingest_drive_files(max_files=None, include_shared=False):
    files = list_drive_files(max_files=max_files, include_shared=include_shared)
    all_chunks = []
    skipped_files = []
    next_progress_report = 40

    for file in files:
        try:
            sections = extract_file_sections(file)
            if file.get("mimeType") == GOOGLE_PRESENTATION_MIME_TYPE:
                chunks = create_presentation_chunks(file, sections)
            else:
                chunks = []
                for section in sections:
                    chunks.extend(
                        create_file_chunks(
                            file,
                            section["text"],
                            section_id=section["section_id"],
                            section_title=section["section_title"],
                            section_label=section["section_label"],
                        )
                    )
            if not chunks:
                skipped_files.append((file.get("name", file["id"]), "No extractable text."))
                continue
            all_chunks.extend(chunks)
            if len(all_chunks) >= next_progress_report:
                print(f"Drive progress: {len(all_chunks)} chunks prepared.")
                next_progress_report = len(all_chunks) + 40
        except Exception as error:
            skipped_files.append((file.get("name", file["id"]), str(error)))
            print(f"Skipped {file.get('name', file['id'])}: {error}")

    if all_chunks:
        add_chunks(all_chunks, "drive")

    print(
        f"\nDone! Ingested {len(all_chunks)} chunks from "
        f"{len(files) - len(skipped_files)} files; skipped {len(skipped_files)} files."
    )
    return len(all_chunks)
