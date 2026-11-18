import re
import sys
import heapq
import string
import sqlite3
import numpy as np
from collections import Counter, defaultdict
from contextlib import closing
import math


words_to_remove = {
    "i", "oraz", "a", "ale", "lecz", "lub", "albo", "bądź",
    "ani", "ni", "czy", "zaś", "natomiast", "jednak", "więc",
    "zatem", "toteż", "dlatego", "przeto", "czyli", "mianowicie",
    "bowiem", "ponieważ", "bo", "gdyż", "albowiem",
    "że", "żeby", "ażeby", "aby", "by", "iż", "aż",
    "choć", "chociaż", "aczkolwiek", "jakkolwiek", "mimo",
    "pomimo", "podczas", "zanim", "nim", "gdy",
    "kiedy", "ilekroć", "skoro", "jeśli", "jeżeli",
    "gdyby", "jeśliby", "jeżeliby", "chyba",
    "tak",
    "zarówno", "jak", "nie", "lecz", "także",
    "również", "bądź", "też",
    "tymczasem", "są", "jest", "to"
}

def CleanQuery(text):
    text = text.lower()
    text = text.replace('\n', ' ').replace('\r', '')
    pattern = re.compile(f"[{re.escape(string.punctuation)}]")
    text = pattern.sub('', text)

    return text

#AI
def Read_docs_vectors(query_vector, db_path="Baza.db"):
    if not query_vector:
        return []

    query_norm = math.sqrt(sum(val ** 2 for val in query_vector.values()))
    if query_norm == 0.0:
        return []

    query_words = list(query_vector.keys())
    placeholders = ','.join(['?'] * len(query_words))

    with closing(sqlite3.connect(db_path)) as db:
        cursor = db.cursor()
        
        cursor.execute(f"""
            SELECT DISTINCT id FROM document_vectors WHERE word IN ({placeholders})
        """, query_words)
        candidate_ids = [row[0] for row in cursor.fetchall()]

        if not candidate_ids:
            return []

        candidate_placeholders = ','.join(['?'] * len(candidate_ids))
        cursor.execute(f"""
            SELECT id, link, word, tfidf FROM document_vectors WHERE id IN ({candidate_placeholders})
        """, candidate_ids)
        rows = cursor.fetchall()

    docs_data = {}
    for doc_id, link, word, tfidf in rows:
        if doc_id not in docs_data:
            docs_data[doc_id] = {"link": link, "vector": {}}
        docs_data[doc_id]["vector"][word] = tfidf

    vectors = []
    
    for doc_id, data in docs_data.items():
        link = data["link"]
        doc_dict = data["vector"]

        doc_norm = math.sqrt(sum(val ** 2 for val in doc_dict.values()))
        if doc_norm == 0.0:
            continue

        dot_product = sum(query_vector[w] * doc_dict[w] for w in query_vector if w in doc_dict)

        score = dot_product / (query_norm * doc_norm)
        vectors.append((doc_id, link, score))

    result = heapq.nlargest(5, vectors, key=lambda x: x[2])
    return result

#AI
def Create_query_vector(query, db_path="Baza.db"):
    with closing(sqlite3.connect(db_path)) as db, db:
        rows = db.execute(
            "SELECT word, idf FROM word_idf"
        ).fetchall()

    idf_values = dict(rows)

    if isinstance(query, str):
        query = query.lower()

        words = [w for w in query.split() if w not in words_to_remove]
    else:
        words = [w for w in query if w not in words_to_remove]

    counts = Counter(words)
    total_words = len(words)

    query_vector = {}
    
    for word, count in counts.items():
        if word in idf_values:
            tf = count / total_words if total_words != 0 else 0
            query_vector[word] = tf * idf_values[word]
    return query_vector

#ai
def PrintResult(result_vectors):
    print("\nBest matches:\n")
    print(f"{'No.':<5} {'ID':<38} {'Filename':<20} {'Score':>10}")
    print("-" * 78)

    for i, (doc_id, filename, score) in enumerate(result_vectors, start=1):
        print(f"{i:<5} {doc_id:<38} {filename:<20} {float(score):>10.4f}")



def main():

    words = ""
    query = []
    
    
    for arg in sys.argv[1:]:
        words += ' ' + arg
    
    words = CleanQuery(words)
    
    for word in words.split():
        if word not in words_to_remove:
            query.append(word)
    
    query_vector = Create_query_vector(query)
    docs = Read_docs_vectors(query_vector)
    
    PrintResult(docs)


if __name__ == "__main__":
    main()