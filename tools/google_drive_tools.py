from config.auth import get_google_service
service = get_google_service("drive", "v3")

'''
=============
connect to google drive but selectively give access to agent
utilize AppData which already stores memory/file of my google account
-> can be utilized by RAG so it doesn't need to re-query google services
figure out what to cache vs. embedd
multi-agent system (google service agents + retrieval agent + synthesis agent)
a lot of week 3 RAG stuff but will keep here for the time being
===========================
'''


def search_drive(query, max_results=5):
    drive_results = service.files().list(
        q=f"fullText contains '{query}'", 
        pageSize=max_results, 
        fields="files(id, name, mimeType, modifiedTime, webViewLink)"
    ).execute()

    mime_type_map = {
        "application/vnd.google-apps.document": "Google Doc",
        "application/vnd.google-apps.spreadsheet": "Google Sheet",
        "application/vnd.google-apps.presentation": "Google Slides",
        "application/vnd.google-apps.folder": "Folder",
        "application/pdf": "PDF",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Doc",
    }

    drive_dict = []
    for item in drive_results["files"]:
        item_dict = {"id": item["id"],
                     "name": item["name"],
                     "mimeType": mime_type_map.get(item["mimeType"], item["mimeType"]),
                     "modifiedTime": item["modifiedTime"],
                     "webViewLink": item["webViewLink"]}
        drive_dict.append(item_dict)
    return drive_dict

def get_file_content(file_id):
    try:
        file_content = service.files().export(
            fileId=file_id,
            mimeType="text/plain"
        ).execute()
        return file_content.decode("utf-8")
    except Exception:
        return "This file type cannot be read as only text" 