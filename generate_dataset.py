"""Generate the deterministic 1000-row spam/ham dataset (script given in the assignment brief)."""
import random
random.seed(42)

SPAM_TEMPLATES = [
    "WIN a FREE {prize} now! Click here: {url}",
    "Congratulations! You have WON a {prize}. Claim NOW at {url}",
    "URGENT: Your account will be suspended. Verify at {url}",
    "Limited time offer! Get {prize} FREE, click {url} today",
    "You've been selected for a {prize}! Reply YES to claim",
    "Cash prize alert: claim your {prize} before it expires! {url}",
]
HAM_TEMPLATES = [
    "Hey, are we still meeting for {activity} on {day}?",
    "Can you send me the notes from {activity} class?",
    "Don't forget about {activity} this {day}, see you there",
    "Thanks for helping with {activity} yesterday",
    "Running a bit late for {activity}, be there in 10 min",
    "What time does {activity} start on {day}?",
]
PRIZES = ["iPhone", "cash prize", "gift card", "vacation", "laptop"]
URLS = ["bit.ly/xyz123", "tinyurl.com/abc", "win-now.co/claim"]
ACTIVITIES = ["lunch", "the study group", "basketball", "the project meeting"]
DAYS = ["Monday", "Friday", "tomorrow", "the weekend"]

rows = []
for i in range(1000):
    if random.random() < 0.3:
        t = random.choice(SPAM_TEMPLATES)
        msg = t.format(prize=random.choice(PRIZES), url=random.choice(URLS))
        rows.append((msg, "spam"))
    else:
        t = random.choice(HAM_TEMPLATES)
        msg = t.format(activity=random.choice(ACTIVITIES), day=random.choice(DAYS))
        rows.append((msg, "ham"))

import pandas as pd
pd.DataFrame(rows, columns=["text", "label"]).to_csv("spam_dataset.csv", index=False)
print(f"wrote spam_dataset.csv  rows={len(rows)}")
print(pd.DataFrame(rows, columns=["text", "label"])["label"].value_counts().to_string())
