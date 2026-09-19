"""Train TF-IDF + MultinomialNB on spam_dataset.csv and save with joblib."""
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

SEED = 42

df = pd.read_csv("spam_dataset.csv")
X, y = df["text"], df["label"]

X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.2, random_state=SEED, stratify=y
)

pipe = Pipeline([
    ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2))),
    ("nb", MultinomialNB()),
])
pipe.fit(X_tr, y_tr)

acc = accuracy_score(y_te, pipe.predict(X_te))
print(f"test accuracy: {acc:.4f}\n")
print(classification_report(y_te, pipe.predict(X_te)))

joblib.dump(pipe, "model.joblib")
print("saved model.joblib")
