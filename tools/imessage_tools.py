import datetime
import sqlite3
import pytz
import os

def search_messages(query, limit=10):
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    eastern = pytz.timezone('US/Eastern')
    apple_epoch = datetime.datetime(2001, 1, 1, tzinfo=pytz.utc)  # make epoch UTC-aware
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT text, date, is_from_me 
            FROM message 
            WHERE text LIKE ? 
            AND text IS NOT NULL
            ORDER BY date DESC 
            LIMIT ?
        ''', (f'%{query}%', limit))
        
        results = cursor.fetchall()

    messages = []
    for text, date, is_from_me in results:
        readable_date = apple_epoch + datetime.timedelta(seconds=date / 1e9)
        readable_date = readable_date.astimezone(eastern)  # convert to Eastern
        messages.append({
            "text": text,
            "date": readable_date.strftime("%Y-%m-%d %I:%M %p"),
            "sender": "Me" if is_from_me else "Them"
        })
    
    return messages

def get_conversation(phone_number, limit=20):
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    apple_epoch = datetime.datetime(2001, 1, 1, tzinfo=pytz.utc)
    eastern = pytz.timezone('US/Eastern')
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.text, m.date, m.is_from_me, m.thread_originator_guid, m.guid
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat_handle_join chj ON cmj.chat_id = chj.chat_id
            JOIN handle h ON chj.handle_id = h.ROWID
            WHERE h.id = ?
            AND m.text IS NOT NULL
            AND cmj.chat_id IN (
                SELECT chat_id FROM chat_handle_join
                GROUP BY chat_id
                HAVING COUNT(*) = 1
            )
            ORDER BY m.date DESC
            LIMIT ?
        ''', (phone_number, limit))
        
        results = cursor.fetchall()
    

    #build a guid -> text map for reply lookup
    guid_to_text = {}
    for text, date, is_from_me, thread_originator_guid, guid in results:
        if guid and text:
            guid_to_text[guid] = text

    messages = []
    for text, date, is_from_me, thread_originator_guid, guid in results:
        readable_date = apple_epoch + datetime.timedelta(seconds=date / 1e9)
        readable_date = readable_date.astimezone(eastern)
        
        reply_to = None
        if thread_originator_guid and thread_originator_guid in guid_to_text:
            reply_to = guid_to_text[thread_originator_guid][:50] + "..."  # truncate to 50 chars
        
        msg = {
            "text": text,
            "date": readable_date.strftime("%Y-%m-%d %I:%M %p"),
            "sender": "Me" if is_from_me else "Them",
        }
        
        if reply_to:
            msg["reply_to"] = reply_to
            
        messages.append(msg)
    
    return messages
    

  

