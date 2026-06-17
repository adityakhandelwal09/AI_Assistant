
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