import re
import sys
import heapq
import string
import sqlite3
import numpy as np
from collections import Counter, defaultdict
from contextlib import closing


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

def Read_docs_vectors(query_vector, db_path="Baza.db"):
    # query_vector to słownik lub wektor numpy odpowiadający słowom z bazy.
    # Załóżmy, że query_vector to słownik: {word: tfidf_value} albo tablica numpy, 
    # ale wygodniej przekazać go jako słownik/wektor z pełnym słownikiem unikalnych słów.
    
    # Najlepiej najpierw pobrać pełną listę słów (vocabulary) z bazy lub zapytania, 
    # aby wektory dokumentu i zapytania miały dokładnie ten sam wymiar i kolejność.
    
    with closing(sqlite3.connect(db_path)) as db, db:
        cursor = db.cursor()
        # Pobieramy wszystkie wpisy z nowej tabeli relacyjnej: id, link, word, tfidf
        cursor.execute("SELECT id, link, word, tfidf FROM document_vectors")
        rows = cursor.fetchall()

    # Grupowanie słów i wartości TF-IDF per dokument (id, link)
    docs_data = defaultdict(dict)
    doc_links = {}
    
    for doc_id, link, word, tfidf in rows:
        docs_data[doc_id][word] = tfidf
        doc_links[doc_id] = link

    # Pobieramy globalną listę słów (lub bierzemy klucze z query_vector, 
    # ale najbezpieczniej dopasować je do unikalnych słów z bazy)
    all_words = sorted(list(set(w for doc in docs_data.values() for w in doc.keys())))
    
    # Tworzymy wektor zapytania jako numpy array w tej samej kolejności słów co dokumenty
    q_vec = np.array([query_vector.get(w, 0.0) for w in all_words], dtype=np.float32)
    query_vector_norm = np.linalg.norm(q_vec)

    vectors = []

    for doc_id, doc_dict in docs_data.items():
        link = doc_links[doc_id]
        
        # Tworzymy wektor dokumentu w tej samej kolejności co zapytanie
        doc_vector = np.array([doc_dict.get(w, 0.0) for w in all_words], dtype=np.float32)
        doc_norm = np.linalg.norm(doc_vector)

        if query_vector_norm == 0 or doc_norm == 0:
            dot_product = 0.0
        else:
            dot_product = np.dot(q_vec / query_vector_norm, doc_vector / doc_norm)

        vectors.append((doc_id, link, dot_product))

    # Zwraca 5 najlepszych dopasowań (id, link, similarity_score)
    result = heapq.nlargest(5, vectors, key=lambda x: x[2])
    return result

def Create_query_vector(query, db_path="Baza.db"):
    with closing(sqlite3.connect(db_path)) as db, db:
        rows = db.execute(
            "SELECT word, idf FROM word_idf"
        ).fetchall()

    idf_values = dict(rows)

    # Jeśli 'query' jest np. stringiem (np. "Józef Poniatowski w Warszawie"), 
    # to najpierw musimy go podzielić na słowa i wyczyścić tak jak w pipeline:
    if isinstance(query, str):
        query = query.lower()
        # Możesz tutaj zastosować ten sam czyszcziciel interpunkcji co w CleanText
        words = [w for w in query.split() if w not in words_to_remove]
    else:
        # Jeśli przekazujesz już listę słów
        words = [w for w in query if w not in words_to_remove]

    counts = Counter(words)
    total_words = len(words)

    query_vector = {}
    
    # Obliczamy TF-IDF tylko dla słów, które występują w zapytaniu ORAZ są w bazie IDF
    for word, count in counts.items():
        if word in idf_values:
            tf = count / total_words if total_words != 0 else 0
            query_vector[word] = tf * idf_values[word]

    # Zwracamy jako słownik: {słowo: wartość_tfidf}
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