from pymongo import MongoClient
from bson import ObjectId
import json

"""
ZEIN Online Bookstore
MongoDB Import Script

Бұл скрипт басқа компьютерде жобаны тез іске қосу үшін арналған.
Скрипт MongoDB-ға барлық негізгі коллекцияларды импорттайды.
"""

# MongoDB байланысы
client = MongoClient("mongodb://localhost:27017/")

# Database атауы
db = client["zein_bookstore"]

print("MongoDB серверіне қосылу сәтті орындалды.")
print("ZEIN деректер қорын импорттау басталды...\n")

# -----------------------------
# BOOKS IMPORT
# -----------------------------

with open("data/books.json", "r", encoding="utf-8") as f:
    books = json.load(f)

db.books.delete_many({})
db.books.insert_many(books)

print(f"Books коллекциясына {len(books)} кітап импортталды.")

# -----------------------------
# USERS IMPORT
# -----------------------------

with open("data/users.json", "r", encoding="utf-8") as f:
    users = json.load(f)

db.users.delete_many({})
db.users.insert_many(users)

print(f"Users коллекциясына {len(users)} пайдаланушы импортталды.")

# -----------------------------
# COURSES IMPORT
# -----------------------------

with open("data/courses.json", "r", encoding="utf-8") as f:
    courses = json.load(f)

db.courses.delete_many({})
db.courses.insert_many(courses)

print(f"Courses коллекциясына {len(courses)} курс импортталды.")

# -----------------------------
# CERTIFICATES IMPORT
# -----------------------------

with open("data/certificates.json", "r", encoding="utf-8") as f:
    certificates = json.load(f)

db.certificates.delete_many({})
db.certificates.insert_many(certificates)

print(f"Certificates коллекциясына {len(certificates)} сертификат импортталды.")

# -----------------------------
# EMPTY COLLECTIONS
# -----------------------------

db.orders.delete_many({})
db.cart.delete_many({})
db.notifications.delete_many({})
db.favorites.delete_many({})
db.cards.delete_many({})
db.reviews.delete_many({})

print("Бос коллекциялар дайындалды:")
print("• orders")
print("• cart")
print("• notifications")
print("• favorites")
print("• cards")
print("• reviews")

print("\nИмпорт аяқталды.")
print("Енді жобаны іске қосуға болады:")
print("python app.py")
