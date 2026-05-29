import os
from datetime import datetime
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-key')

# MongoDB connection
client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
db = client[os.getenv('DB_NAME', 'bookstore_db')]

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Алдымен жүйеге кіріңіз'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.name = user_data['name']
        self.role = user_data.get('role', 'client')
        self.bonuses = user_data.get('bonuses', 0)
        self.favorite_genres = user_data.get('favorite_genres', [])
        self.saved_cards = user_data.get('saved_cards', [])
        self.avatar_url = user_data.get('avatar_url', '')

@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = db.users.find_one({'_id': ObjectId(user_id)})
        return User(user_data) if user_data else None
    except:
        return None

# ---------- Вспомогательные функции ----------
def get_cart_count(user_id):
    if not user_id: return 0
    return db.cart.count_documents({'user_id': user_id})

def get_favorites_count(user_id):
    if not user_id: return 0
    return db.favorites.count_documents({'user_id': user_id})

def get_genre_counts():
    pipeline = [{'$group': {'_id': '$genre', 'count': {'$sum': 1}}}]
    counts = list(db.books.aggregate(pipeline))
    return {item['_id']: item['count'] for item in counts}

def get_popular_books(limit=8):
    pipeline = [
        {'$unwind': '$items'},
        {'$group': {'_id': '$items.book_id', 'sold_count': {'$sum': '$items.quantity'}}},
        {'$sort': {'sold_count': -1}},
        {'$limit': limit}
    ]
    result = list(db.orders.aggregate(pipeline))
    books = []
    used = set()
    for row in result:
        try:
            bid = row['_id']
            book = db.books.find_one({'_id': ObjectId(bid)}) if not isinstance(bid, ObjectId) else db.books.find_one({'_id': bid})
            if book:
                book['sold_count'] = row.get('sold_count', 0)
                books.append(book)
                used.add(str(book['_id']))
        except Exception:
            pass
    if len(books) < limit:
        for book in db.books.find().sort('popularity', -1).limit(limit * 2):
            if str(book['_id']) not in used:
                books.append(book)
            if len(books) >= limit:
                break
    return books

def get_genre_showcase(limit=6):
    data = []
    for genre in db.books.distinct('genre')[:limit]:
        books = list(db.books.find({'genre': genre}).sort('popularity', -1).limit(3))
        data.append({'name': genre, 'books': books})
    return data

def format_price(price):
    try:
        return f"{int(price):,}".replace(',', ' ') + " ₸"
    except Exception:
        return "0 ₸"

app.jinja_env.filters['format_price'] = format_price

def short_id(value, prefix='ID'):
    try:
        s = str(value)
        return f"{prefix}-{s[-6:].upper()}"
    except Exception:
        return f"{prefix}-000000"

app.jinja_env.filters['short_id'] = short_id

def get_user_name(user_id):
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
        return user.get('name', user_id) if user else user_id
    except Exception:
        return user_id

def get_notifications_count(user_id):
    if not user_id:
        return 0
    return db.notifications.count_documents({'user_id': user_id, 'is_read': False})

def get_certificate_count(user_id):
    if not user_id:
        return 0
    return db.certificates.count_documents({'user_id': user_id})

def next_code(collection_name, prefix):
    seq = db.counters.find_one_and_update(
        {'_id': collection_name},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=True
    )
    return f"{prefix}-{seq.get('seq', 1):04d}"


@app.context_processor
def utility_processor():
    return {
        'get_cart_count': get_cart_count,
        'get_favorites_count': get_favorites_count,
        'format_price': format_price,
        'site_name': 'Zein',
        'get_notifications_count': get_notifications_count,
        'get_certificate_count': get_certificate_count,
        'get_user_name': get_user_name
    }


# ---------- Главная ----------
@app.route('/')
def index():
    new_books = list(db.books.find().sort('created_at', -1).limit(8))
    popular_books = get_popular_books(8)

    if current_user.is_authenticated:
        user = db.users.find_one({'_id': ObjectId(current_user.id)})
        fav_genres = user.get('favorite_genres', []) if user else []
        recommended_books = list(db.books.find({'genre': {'$in': fav_genres}}).limit(8)) if fav_genres else list(db.books.find().sort('popularity', -1).limit(8))
    else:
        recommended_books = list(db.books.find().sort('popularity', -1).limit(8))

    genre_counts = get_genre_counts()
    genres_showcase = get_genre_showcase(8)
    publishers = db.books.distinct('publisher')

    posts = list(db.posts.aggregate([
        {'$lookup': {'from': 'users', 'localField': 'user_id', 'foreignField': '_id', 'as': 'user'}},
        {'$unwind': '$user'},
        {'$lookup': {'from': 'books', 'localField': 'book_id', 'foreignField': '_id', 'as': 'book'}},
        {'$unwind': '$book'},
        {'$sort': {'created_at': -1}},
        {'$limit': 4}
    ]))
    return render_template('index.html', new_books=new_books, popular_books=popular_books,
                           recommended_books=recommended_books, genre_counts=genre_counts,
                           genres_showcase=genres_showcase, publishers=publishers, posts=posts)

# ---------- Каталог ----------
@app.route('/catalog')
def catalog():
    search = request.args.get('search', '').strip()
    genre = request.args.get('genre', '').strip()
    publisher = request.args.get('publisher', '').strip()
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 24
    query = {}
    if search:
        query['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'author': {'$regex': search, '$options': 'i'}},
            {'publisher': {'$regex': search, '$options': 'i'}}
        ]
    if genre and genre != 'all':
        query['genre'] = genre
    if publisher and publisher != 'all':
        query['publisher'] = publisher
    sort_mapping = {'price': 'price', 'popularity': 'popularity', 'rating': 'rating', 'created_at': 'created_at'}
    sort_field = sort_mapping.get(sort, 'created_at')
    sort_direction = -1 if order == 'desc' else 1
    total_books = db.books.count_documents(query)
    total_pages = max((total_books + per_page - 1) // per_page, 1)
    if page > total_pages:
        page = total_pages
    books = list(db.books.find(query).sort(sort_field, sort_direction).skip((page - 1) * per_page).limit(per_page))
    genres = db.books.distinct('genre')
    publishers = db.books.distinct('publisher')
    return render_template('catalog.html', books=books, genres=genres, publishers=publishers,
                           search=search, genre=genre, publisher=publisher, sort=sort, order=order,
                           page=page, total_pages=total_pages, total_books=total_books)

# ---------- Детали книги ----------
@app.route('/book/<book_id>')
def book_detail(book_id):
    try:
        book = db.books.find_one({'_id': ObjectId(book_id)})
        if not book:
            flash('Кітап табылмады', 'danger')
            return redirect(url_for('catalog'))
        reviews = list(db.reviews.aggregate([
            {'$match': {'book_id': ObjectId(book_id)}},
            {'$lookup': {'from': 'users', 'localField': 'user_id', 'foreignField': '_id', 'as': 'user'}},
            {'$unwind': '$user'},
            {'$sort': {'created_at': -1}}
        ]))
        similar = list(db.books.find({'genre': book['genre'], '_id': {'$ne': ObjectId(book_id)}}).limit(6))
        same_author = list(db.books.find({'author': book['author'], '_id': {'$ne': ObjectId(book_id)}}).limit(6))
        return render_template('book_detail.html', book=book, reviews=reviews, similar=similar, same_author=same_author)
    except:
        flash('Кітапты жүктеу кезінде қате шықты', 'danger')
        return redirect(url_for('catalog'))

# ---------- Корзина ----------
@app.route('/add_to_cart/<book_id>', methods=['POST'])
@login_required
def add_to_cart(book_id):
    try:
        quantity = int(request.form.get('quantity', 1))
        book = db.books.find_one({'_id': ObjectId(book_id)})
        if not book:
            flash('Кітап табылмады', 'danger')
            return redirect(request.referrer or url_for('catalog'))
        if book['stock'] < quantity:
            flash(f'Недостаточно книг. Доступно: {book["stock"]}', 'danger')
            return redirect(request.referrer or url_for('catalog'))
        existing = db.cart.find_one({'user_id': current_user.id, 'book_id': ObjectId(book_id)})
        if existing:
            new_qty = existing['quantity'] + quantity
            if new_qty > book['stock']:
                flash('Слишком много', 'danger')
                return redirect(request.referrer or url_for('catalog'))
            db.cart.update_one({'_id': existing['_id']}, {'$set': {'quantity': new_qty}})
        else:
            db.cart.insert_one({'user_id': current_user.id, 'book_id': ObjectId(book_id), 'quantity': quantity, 'added_at': datetime.utcnow()})
        flash(f'"{book["title"]}" кітабы себетке қосылды', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(request.referrer or url_for('catalog'))

@app.route('/cart')
@login_required
def cart():
    cart_items = []
    total = 0
    for item in db.cart.find({'user_id': current_user.id}):
        item_type = item.get('item_type', 'book')
        if item_type == 'certificate':
            price = int(item.get('amount', 0))
            qty = int(item.get('quantity', 1))
            item_total = price * qty
            total += item_total
            cart_items.append({
                'cart_id': str(item['_id']),
                'book_id': '',
                'item_type': 'certificate',
                'title': f"Сыйлық сертификаты {format_price(price)}",
                'author': item.get('receiver') or 'Zein сертификаты',
                'price': price,
                'quantity': qty,
                'stock': 99,
                'image_url': 'https://placehold.co/300x420/111111/ffffff?text=ZEIN+GIFT',
                'total': item_total,
                'wish': item.get('wish', '')
            })
            continue
        book = db.books.find_one({'_id': item.get('book_id')})
        if book:
            item_total = book['price'] * item['quantity']
            total += item_total
            cart_items.append({
                'cart_id': str(item['_id']),
                'book_id': str(book['_id']),
                'item_type': 'book',
                'title': book['title'],
                'author': book['author'],
                'price': book['price'],
                'quantity': item['quantity'],
                'stock': book.get('stock', 1),
                'image_url': book.get('image_url', ''),
                'total': item_total
            })
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart/<cart_id>', methods=['POST'])
@login_required
def update_cart(cart_id):
    try:
        quantity = int(request.form['quantity'])
        if quantity <= 0:
            db.cart.delete_one({'_id': ObjectId(cart_id), 'user_id': current_user.id})
            flash('Товар удалён', 'info')
        else:
            cart_item = db.cart.find_one({'_id': ObjectId(cart_id), 'user_id': current_user.id})
            if cart_item:
                
                if cart_item.get('item_type') == 'certificate':
                    db.cart.update_one({'_id': ObjectId(cart_id)}, {'$set': {'quantity': quantity}})
                    flash('Саны жаңартылды', 'success')
                    return redirect(url_for('cart'))
                book = db.books.find_one({'_id': cart_item['book_id']})
                if book and book['stock'] >= quantity:
                    db.cart.update_one({'_id': ObjectId(cart_id)}, {'$set': {'quantity': quantity}})
                    flash('Количество обновлено', 'success')
                else:
                    flash(f'Недостаточно товара. Доступно: {book["stock"] if book else 0}', 'danger')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<cart_id>')
@login_required
def remove_from_cart(cart_id):
    db.cart.delete_one({'_id': ObjectId(cart_id), 'user_id': current_user.id})
    flash('Товар удалён', 'info')
    return redirect(url_for('cart'))

# ---------- Избранное ----------
@app.route('/favorites')
@login_required
def favorites():
    fav_books = []
    for fav in db.favorites.find({'user_id': current_user.id}):
        book = db.books.find_one({'_id': fav['book_id']})
        if book:
            fav_books.append(book)
    return render_template('favorites.html', favorites=fav_books)

@app.route('/toggle_favorite/<book_id>')
@login_required
def toggle_favorite(book_id):
    existing = db.favorites.find_one({'user_id': current_user.id, 'book_id': ObjectId(book_id)})
    if existing:
        db.favorites.delete_one({'_id': existing['_id']})
        flash('Таңдаулыдан өшірілді', 'info')
    else:
        db.favorites.insert_one({'user_id': current_user.id, 'book_id': ObjectId(book_id)})
        flash('Таңдаулыға қосылды', 'success')
    return redirect(request.referrer or url_for('catalog'))

# ---------- Оформление заказа ----------
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = list(db.cart.find({'user_id': current_user.id}))
    if not cart_items:
        flash('Себет бос', 'warning')
        return redirect(url_for('cart'))

    items = []
    subtotal = 0

    for item in cart_items:
        if item.get('item_type') == 'certificate':
            price = int(item.get('amount', 0))
            qty = int(item.get('quantity', 1))
            subtotal += price * qty
            items.append({
                'item_type': 'certificate',
                'book_id': None,
                'title': f"Сыйлық сертификаты {format_price(price)}",
                'price': price,
                'quantity': qty,
                'stock': 99,
                'receiver': item.get('receiver', ''),
                'wish': item.get('wish', '')
            })
            continue

        book = db.books.find_one({'_id': item.get('book_id')})
        if book:
            subtotal += book['price'] * item['quantity']
            items.append({
                'item_type': 'book',
                'book_id': str(book['_id']),
                'title': book['title'],
                'price': book['price'],
                'quantity': item['quantity'],
                'stock': book.get('stock', 0)
            })

    user = db.users.find_one({'_id': ObjectId(current_user.id)})
    available_bonuses = user.get('bonuses', 0) if user else 0

    saved_cards = list(db.cards.find({
        'user_id': current_user.id,
        'is_active': True
    }).sort('created_at', -1))

    if request.method == 'POST':
        try:
            certificate_code = request.form.get('certificate_code', '').strip().upper()
            certificate_discount = 0
            certificate = None

            if certificate_code:
                certificate = db.certificates.find_one({
                    'code': certificate_code,
                    'user_id': current_user.id,
                    'status': {'$in': ['active', 'delivered', 'sent', 'purchased']}
                })

                if not certificate:
                    flash('Сертификат табылмады немесе қолданылған', 'danger')
                    return render_template(
                        'checkout.html',
                        items=items,
                        subtotal=subtotal,
                        available_bonuses=available_bonuses,
                        saved_cards=saved_cards
                    )

                certificate_discount = min(int(certificate.get('balance', 0)), subtotal)

            use_bonuses = 'use_bonuses' in request.form
            bonus_amount = min(available_bonuses, subtotal - certificate_discount) if use_bonuses else 0
            final_price = max(0, subtotal - certificate_discount - bonus_amount)

            use_saved_card = 'use_saved_card' in request.form
            saved_card_id = request.form.get('saved_card_id', '').strip()

            card_number = '0000000000000000'
            expiry = ''
            cvv = ''
            card_holder = current_user.name
            card_last4 = '0000'
            save_card = False

            if final_price > 0:
                if use_saved_card:
                    if not saved_card_id:
                        flash('Сақталған картаны таңдаңыз', 'danger')
                        return render_template(
                            'checkout.html',
                            items=items,
                            subtotal=subtotal,
                            available_bonuses=available_bonuses,
                            saved_cards=saved_cards
                        )

                    saved_card = db.cards.find_one({
                        '_id': ObjectId(saved_card_id),
                        'user_id': current_user.id,
                        'is_active': True
                    })

                    if not saved_card:
                        flash('Сақталған карта табылмады', 'danger')
                        return render_template(
                            'checkout.html',
                            items=items,
                            subtotal=subtotal,
                            available_bonuses=available_bonuses,
                            saved_cards=saved_cards
                        )

                    card_last4 = saved_card.get('last4', '0000')
                    card_holder = saved_card.get('card_holder', current_user.name)

                else:
                    card_number = request.form.get('card_number', '').replace(' ', '')
                    expiry = request.form.get('expiry', '').strip()
                    cvv = request.form.get('cvv', '').strip()
                    card_holder = request.form.get('card_holder', '').strip()
                    save_card = 'save_card' in request.form

                    if not (
                        re.fullmatch(r'\d{16}', card_number)
                        and re.fullmatch(r'\d{3}', cvv)
                        and re.fullmatch(r'(0[1-9]|1[0-2])\/\d{2}', expiry)
                        and card_holder
                    ):
                        flash('Карта деректері дұрыс емес', 'danger')
                        return render_template(
                            'checkout.html',
                            items=items,
                            subtotal=subtotal,
                            available_bonuses=available_bonuses,
                            saved_cards=saved_cards
                        )

                    card_last4 = card_number[-4:]

            for item in items:
                if item.get('item_type') == 'book':
                    book = db.books.find_one({'_id': ObjectId(item['book_id'])})
                    if not book or book.get('stock', 0) < item['quantity']:
                        flash(f'«{item["title"]}» кітабы жеткіліксіз', 'danger')
                        return redirect(url_for('cart'))

            order_code = next_code('orders', 'ORDER')

            order = {
                'order_code': order_code,
                'user_id': current_user.id,
                'items': items,
                'subtotal': subtotal,
                'used_certificate': certificate_discount,
                'certificate_code': certificate_code if certificate_discount else '',
                'used_bonuses': bonus_amount,
                'final_price': final_price,
                'payment_method': 'certificate' if final_price == 0 else 'card',
                'status': 'Қабылданды',
                'created_at': datetime.utcnow(),
                'card_last4': card_last4
            }

            result = db.orders.insert_one(order)

            for item in items:
                if item.get('item_type') == 'book':
                    db.books.update_one(
                        {'_id': ObjectId(item['book_id'])},
                        {'$inc': {'stock': -item['quantity'], 'sold_count': item['quantity']}}
                    )

                elif item.get('item_type') == 'certificate':
                    for _ in range(item['quantity']):
                        code = next_code('certificates', 'ZEIN')
                        db.certificates.insert_one({
                            'code': code,
                            'amount': int(item['price']),
                            'balance': int(item['price']),
                            'status': 'purchased',
                            'user_id': current_user.id,
                            'receiver': item.get('receiver', ''),
                            'wish': item.get('wish', ''),
                            'created_at': datetime.utcnow(),
                            'order_id': str(result.inserted_id)
                        })

                        db.notifications.insert_one({
                            'user_id': current_user.id,
                            'title': 'Сертификат дайын',
                            'message': f'Сыйлық сертификатыңыздың коды: {code}. Профильдегі сертификаттар бөлімінен көре аласыз.',
                            'is_read': False,
                            'created_at': datetime.utcnow(),
                            'order_id': str(result.inserted_id)
                        })

            if certificate_discount > 0 and certificate:
                new_balance = int(certificate.get('balance', 0)) - certificate_discount
                db.certificates.update_one(
                    {'_id': certificate['_id']},
                    {'$set': {
                        'balance': new_balance,
                        'status': 'used' if new_balance <= 0 else 'active',
                        'used_at': datetime.utcnow()
                    }}
                )

            if bonus_amount > 0:
                db.users.update_one(
                    {'_id': ObjectId(current_user.id)},
                    {'$inc': {'bonuses': -bonus_amount}}
                )

            earned_bonuses = int(final_price * 0.05)
            db.users.update_one(
                {'_id': ObjectId(current_user.id)},
                {'$inc': {'bonuses': earned_bonuses}}
            )

            if final_price > 0 and not use_saved_card and save_card:
                existing_card = db.cards.find_one({
                    'user_id': current_user.id,
                    'last4': card_last4,
                    'expiry': expiry,
                    'card_holder': card_holder
                })

                if not existing_card:
                    db.cards.insert_one({
                        'user_id': current_user.id,
                        'last4': card_last4,
                        'expiry': expiry,
                        'card_holder': card_holder,
                        'card_type': 'Visa / Mastercard',
                        'is_active': True,
                        'created_at': datetime.utcnow()
                    })

            db.cart.delete_many({'user_id': current_user.id})

            db.notifications.insert_one({
                'user_id': current_user.id,
                'title': 'Тапсырыс қабылданды',
                'message': f'{order_code} тапсырысыңыз қабылданды.',
                'is_read': False,
                'created_at': datetime.utcnow(),
                'order_id': str(result.inserted_id)
            })

            flash(f'Тапсырыс сәтті рәсімделді! Бонус: {earned_bonuses} ₸', 'success')
            return redirect(url_for('orders'))

        except Exception as e:
            flash(f'Қате: {str(e)}', 'danger')
            return redirect(url_for('cart'))

    return render_template(
        'checkout.html',
        items=items,
        subtotal=subtotal,
        available_bonuses=available_bonuses,
        saved_cards=saved_cards
    )

# ---------- Заказы ----------
@app.route('/orders')
@login_required
def orders():
    try:
        user_orders = list(db.orders.find({'user_id': current_user.id}).sort('created_at', -1))
        return render_template('orders.html', orders=user_orders)
    except Exception as e:
        flash(f'Ошибка загрузки заказов: {str(e)}', 'danger')
        return render_template('orders.html', orders=[])

# ---------- Отзывы ----------
@app.route('/add_review/<book_id>', methods=['POST'])
@login_required
def add_review(book_id):
    try:
        rating = int(request.form['rating'])
        text = request.form['text'].strip()
        if len(text) < 5:
            flash('Отзыв слишком короткий', 'danger')
            return redirect(url_for('book_detail', book_id=book_id))
        review = {
            'user_id': current_user.id,
            'book_id': ObjectId(book_id),
            'rating': rating,
            'text': text,
            'created_at': datetime.utcnow()
        }
        db.reviews.insert_one(review)
        # Обновление среднего рейтинга книги
        pipeline = [{'$match': {'book_id': ObjectId(book_id)}}, {'$group': {'_id': None, 'avg': {'$avg': '$rating'}}}]
        result = list(db.reviews.aggregate(pipeline))
        avg = result[0]['avg'] if result else 0
        db.books.update_one({'_id': ObjectId(book_id)}, {'$set': {'rating': round(avg, 1)}})
        flash('Отзыв добавлен', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('book_detail', book_id=book_id))

# ---------- Посты ----------
@app.route('/add_post', methods=['POST'])
@login_required
def add_post():
    try:
        book_id = request.form['book_id']
        text = request.form['text'].strip()
        if len(text) < 10:
            flash('Пост слишком короткий', 'danger')
            return redirect(request.referrer or url_for('index'))
        db.posts.insert_one({
            'user_id': current_user.id,
            'book_id': ObjectId(book_id),
            'text': text,
            'created_at': datetime.utcnow()
        })
        flash('Пост опубликован', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(request.referrer or url_for('index'))

# ---------- Профиль (с отзывами, картами, заказами) ----------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = db.users.find_one({'_id': ObjectId(current_user.id)})
    if request.method == 'POST':
        try:
            new_name = request.form.get('name')
            new_email = request.form.get('email')
            avatar_url = request.form.get('avatar_url', '')
            if new_name:
                db.users.update_one({'_id': ObjectId(current_user.id)}, {'$set': {'name': new_name, 'email': new_email, 'avatar_url': avatar_url}})
            # Любимые жанры
            fav_genres = request.form.getlist('favorite_genres')
            db.users.update_one({'_id': ObjectId(current_user.id)}, {'$set': {'favorite_genres': fav_genres}})
            flash('Профиль жаңартылды', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            flash(f'Қате: {str(e)}', 'danger')
    # Получаем отзывы пользователя
    user_reviews = list(db.reviews.aggregate([
        {'$match': {'user_id': current_user.id}},
        {'$lookup': {'from': 'books', 'localField': 'book_id', 'foreignField': '_id', 'as': 'book'}},
        {'$unwind': '$book'},
        {'$sort': {'created_at': -1}}
    ]))
    # Получаем последние заказы
    recent_orders = list(db.orders.find({'user_id': current_user.id}).sort('created_at', -1).limit(5))
    notifications = list(db.notifications.find({'user_id': current_user.id}).sort('created_at', -1).limit(5))
    course_requests = list(db.course_requests.find({'user_id': current_user.id}).sort('created_at', -1).limit(10))
    certificates = list(db.certificates.find({'user_id': current_user.id}).sort('created_at', -1).limit(8))
    all_genres = db.books.distinct('genre')
    return render_template('profile.html', user=user, user_reviews=user_reviews, recent_orders=recent_orders, all_genres=all_genres, notifications=notifications, course_requests=course_requests, certificates=certificates)


# ---------- Хабарламалар ----------
@app.route('/notifications')
@login_required
def notifications():
    page = max(int(request.args.get('page', 1) or 1), 1)
    status = request.args.get('status', 'all')
    per_page = 10
    query = {'user_id': current_user.id}
    if status == 'unread':
        query['is_read'] = False
    elif status == 'read':
        query['is_read'] = True
    total = db.notifications.count_documents(query)
    total_pages = max((total + per_page - 1) // per_page, 1)
    if page > total_pages:
        page = total_pages
    notifications = list(db.notifications.find(query).sort('created_at', -1).skip((page-1)*per_page).limit(per_page))
    return render_template('notifications.html', notifications=notifications, page=page, total_pages=total_pages, status=status, total=total)

@app.route('/notifications/mark_read/<notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    db.notifications.update_one({'_id': ObjectId(notification_id), 'user_id': current_user.id}, {'$set': {'is_read': True}})
    return redirect(request.referrer or url_for('notifications'))

@app.route('/notifications/mark_unread/<notification_id>', methods=['POST'])
@login_required
def mark_notification_unread(notification_id):
    db.notifications.update_one({'_id': ObjectId(notification_id), 'user_id': current_user.id}, {'$set': {'is_read': False}})
    return redirect(request.referrer or url_for('notifications'))

@app.route('/notifications/mark_all_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    db.notifications.update_many({'user_id': current_user.id, 'is_read': False}, {'$set': {'is_read': True}})
    flash('Барлық хабарлама оқылды деп белгіленді', 'success')
    return redirect(url_for('notifications'))

# ---------- Сертификаттар ----------
@app.route('/certificates')
@login_required
def certificates():
    user_certificates = list(db.certificates.find({'user_id': current_user.id}).sort('created_at', -1))
    return render_template('certificates.html', certificates=user_certificates)

@app.route('/api/check_certificate')
@login_required
def api_check_certificate():
    code = request.args.get('code', '').strip().upper()
    subtotal = int(request.args.get('subtotal', 0) or 0)
    cert = db.certificates.find_one({'code': code, 'user_id': current_user.id, 'status': {'$in': ['active','delivered','sent','purchased']}})
    if not cert:
        return jsonify({'ok': False, 'message': 'Сертификат табылмады немесе қолданылған'})
    balance = int(cert.get('balance', 0))
    discount = min(balance, subtotal) if subtotal else balance
    return jsonify({'ok': True, 'code': code, 'balance': balance, 'discount': discount, 'status': cert.get('status','active')})

# ---------- Админ-панель (только для админа) ----------
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Қолжетімділік жоқ', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_users = db.users.count_documents({'role': 'client'})
    total_orders = db.orders.count_documents({})
    total_books = db.books.count_documents({})
    low_stock = db.books.count_documents({'stock': {'$lt': 5}})
    all_orders = list(db.orders.find().sort('created_at', -1).limit(5))
    return render_template('admin_dashboard.html', total_users=total_users, total_orders=total_orders,
                           total_books=total_books, low_stock=low_stock, all_orders=all_orders)

@app.route('/admin/users')
@admin_required
def admin_users():
    users = list(db.users.find({'role': 'client'}).sort('created_at', -1))
    return render_template('admin_users.html', users=users)

@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = list(db.orders.find().sort('created_at', -1))
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/books')
@admin_required
def admin_books():
    books = list(db.books.find().sort('created_at', -1))
    return render_template('admin_books.html', books=books)

@app.route('/admin/low_stock')
@admin_required
def admin_low_stock():
    books = list(db.books.find({'stock': {'$lt': 5}}))
    return render_template('admin_books.html', books=books, low_stock_only=True)

@app.route('/admin/add_book', methods=['POST'])
@admin_required
def admin_add_book():
    try:
        book_data = {
            'title': request.form['title'],
            'author': request.form['author'],
            'description': request.form['description'],
            'genre': request.form['genre'],
            'publisher': request.form.get('publisher', 'Zein баспасы'),
            'tags': request.form.get('tags', '').split(','),
            'price': int(request.form['price']),
            'stock': int(request.form['stock']),
            'image_url': request.form['image_url'],
            'rating': 0,
            'is_new': 'is_new' in request.form,
            'popularity': 50,
            'created_at': datetime.utcnow()
        }
        db.books.insert_one(book_data)
        flash('Кітап қосылды', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('admin_books'))

@app.route('/admin/edit_book/<book_id>', methods=['POST'])
@admin_required
def admin_edit_book(book_id):
    try:
        db.books.update_one({'_id': ObjectId(book_id)}, {'$set': {
            'title': request.form['title'],
            'author': request.form['author'],
            'description': request.form['description'],
            'genre': request.form['genre'],
            'publisher': request.form.get('publisher', 'Zein баспасы'),
            'price': int(request.form['price']),
            'stock': int(request.form['stock']),
            'image_url': request.form['image_url']
        }})
        flash('Кітап жаңартылды', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('admin_books'))

@app.route('/admin/delete_book/<book_id>')
@admin_required
def admin_delete_book(book_id):
    try:
        db.books.delete_one({'_id': ObjectId(book_id)})
        flash('Кітап өшірілді', 'danger')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('admin_books'))

@app.route('/admin/update_order_status/<order_id>', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    try:
        new_status = request.form['status']
        custom_message = request.form.get('message', '').strip()
        order = db.orders.find_one({'_id': ObjectId(order_id)})
        db.orders.update_one({'_id': ObjectId(order_id)}, {'$set': {'status': new_status}})
        default_messages = {
            'Қабылданды': 'Тапсырысыңыз қабылданды.',
            'Жиналып жатыр': 'Тапсырысыңыз қазір жиналып жатыр.',
            'Жиналды': 'Тапсырысыңыз жиналды және жіберуге дайын.',
            'Жолда': 'Тапсырысыңыз жолда.',
            'Пунктке келді': 'Тапсырысыңыз пунктке келді. Профильден қарап, алған соң растаңыз.',
            'Алынды': 'Тапсырысыңыз алынған деп белгіленді.',
            'Бас тартылды': 'Тапсырыстан бас тартылды.'
        }
        if order:
            db.notifications.insert_one({'user_id': order['user_id'], 'title': f'Тапсырыс статусы: {new_status}', 'message': custom_message or default_messages.get(new_status, 'Тапсырыс статусы өзгерді.'), 'is_read': False, 'created_at': datetime.utcnow(), 'order_id': str(order['_id'])})
        flash('Статус жаңартылды және хабарлама жіберілді', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('admin_orders'))


@app.route('/confirm_received/<order_id>', methods=['POST'])
@login_required
def confirm_received(order_id):
    db.orders.update_one({'_id': ObjectId(order_id), 'user_id': current_user.id}, {'$set': {'status': 'Алынды', 'received_at': datetime.utcnow()}})
    flash('Тапсырыс алынған деп белгіленді', 'success')
    return redirect(url_for('orders'))

@app.route('/gift_certificate', methods=['POST'])
@login_required
def gift_certificate():
    amount = int(request.form.get('amount', 5000))
    wish = request.form.get('wish', '').strip()
    receiver = request.form.get('receiver', '').strip()
    db.cart.insert_one({'user_id': current_user.id, 'item_type': 'certificate', 'amount': amount, 'receiver': receiver, 'wish': wish, 'quantity': 1, 'added_at': datetime.utcnow()})
    flash('Сыйлық сертификаты себетке қосылды. Енді себет арқылы төлей аласыз.', 'success')
    return redirect(url_for('cart'))

@app.route('/language_course', methods=['POST'])
@login_required
def language_course():
    req = {
        'user_id': current_user.id,
        'language': request.form.get('language'),
        'format': request.form.get('format'),
        'level': request.form.get('level'),
        'schedule': request.form.get('schedule'),
        'teacher': request.form.get('teacher'),
        'comment': request.form.get('comment', ''),
        'status': 'Жаңа өтінім',
        'created_at': datetime.utcnow()
    }
    result = db.course_requests.insert_one(req)
    db.notifications.insert_one({'user_id': current_user.id, 'title': 'Курсқа өтінім жіберілді', 'message': 'Өтінім қабылданды. Админ қарап, жауап береді.', 'is_read': False, 'created_at': datetime.utcnow(), 'course_request_id': str(result.inserted_id)})
    flash('Тіл курсына өтінім жіберілді. Жауап профильдегі хабарламаларға келеді.', 'success')
    return redirect(url_for('profile'))

@app.route('/admin/courses')
@admin_required
def admin_courses():
    requests = list(db.course_requests.find().sort('created_at', -1))
    return render_template('admin_courses.html', requests=requests)

@app.route('/admin/update_course/<request_id>', methods=['POST'])
@admin_required
def admin_update_course(request_id):
    try:
        new_status = request.form.get('status')
        message = request.form.get('message', '').strip()
        course = db.course_requests.find_one({'_id': ObjectId(request_id)})
        db.course_requests.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': new_status, 'admin_message': message, 'updated_at': datetime.utcnow()}})
        if course:
            db.notifications.insert_one({'user_id': course['user_id'], 'title': f'Курс өтінімі: {new_status}', 'message': message or 'Курс өтінімінің статусы өзгерді.', 'is_read': False, 'created_at': datetime.utcnow(), 'course_request_id': str(course['_id'])})
        flash('Курс өтінімі жаңартылды', 'success')
    except Exception as e:
        flash(f'Қате: {str(e)}', 'danger')
    return redirect(url_for('admin_courses'))


@app.route('/admin/certificates')
@admin_required
def admin_certificates():
    certificates = list(db.certificates.find().sort('created_at', -1))
    return render_template('admin_certificates.html', certificates=certificates)

@app.route('/admin/update_certificate/<cert_id>', methods=['POST'])
@admin_required
def admin_update_certificate(cert_id):
    new_status = request.form.get('status')
    cert = db.certificates.find_one({'_id': ObjectId(cert_id)})
    db.certificates.update_one({'_id': ObjectId(cert_id)}, {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}})
    if cert:
        status_text = {'purchased':'сатып алынды','sent':'жіберілді','delivered':'жеткізілді','used':'қолданылды','active':'белсенді'}
        db.notifications.insert_one({'user_id': cert['user_id'], 'title': 'Сертификат статусы', 'message': f'{cert["code"]} сертификаты: {status_text.get(new_status, new_status)}.', 'is_read': False, 'created_at': datetime.utcnow()})
    flash('Сертификат статусы жаңартылды', 'success')
    return redirect(url_for('admin_certificates'))

# ---------- Аутентификация ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            if db.users.find_one({'email': email}):
                flash('Бұл email бұрын тіркелген', 'danger')
                return redirect(url_for('register'))
            db.users.insert_one({
                'name': name,
                'email': email,
                'password': password,
                'role': 'client',
                'favorite_genres': [],
                'bonuses': 200,
                'saved_cards': [],
                'avatar_url': '',
                'created_at': datetime.utcnow()
            })
            flash('Тіркелу сәтті өтті! Енді кіріңіз', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Қате: {str(e)}', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_data = db.users.find_one({'email': email})
        if user_data and user_data['password'] == password:
            login_user(User(user_data))
            flash(f'Қош келдіңіз, {user_data["name"]}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Email немесе құпиясөз дұрыс емес', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Сіз жүйеден шықтыңыз', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)