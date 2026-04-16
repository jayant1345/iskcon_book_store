"""
Seed database with ISKCON categories and books.
Run: python seed_data.py
"""

from app import app, db, Category, Book, Coupon
from datetime import datetime, timedelta


CATEGORIES = [
    {"name": "Paper Copy", "slug": "paper-copy", "icon": "📗", "sort_order": 1,
     "description": "Physical books in English, Hindi & Gujarati by Srila Prabhupada"},
    {"name": "E-Book",     "slug": "e-book",     "icon": "📱", "sort_order": 2,
     "description": "Digital eBooks in English, Hindi & Gujarati – instant download"},
]


BOOKS = [
    # ── Paper Copy — English ──
    {
        "title": "Bhagavad Gita As It Is (Large, Hard Cover)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 350.0, "original_price": 550.0,
        "language": "English", "pages": 924,
        "featured": True, "stock": 200,
        "short_desc": "The complete authorized edition with original Sanskrit, transliteration, word-for-word translation, and elaborate purports.",
        "description": "The Bhagavad-gita is universally renowned as the jewel of India's spiritual wisdom. Spoken by Lord Sri Krishna to His disciple Arjuna, the Gita's 700 verses provide a definitive guide to the science of self-realization. Includes original Sanskrit, Roman transliteration, word-for-word synonyms, translation, and elaborate purports by Srila Prabhupada.",
    },
    {
        "title": "Bhagavad Gita As It Is (Pocket Size)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 110.0, "original_price": 150.0,
        "language": "English", "pages": 924,
        "featured": False, "stock": 500,
        "short_desc": "Compact pocket edition – perfect for on-the-go reading.",
        "description": "Same complete authorized translation in a convenient pocket size. Includes all 700 verses with purports by Srila Prabhupada.",
    },
    {
        "title": "Srimad Bhagavatam – Complete 18-Volume Set",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 4500.0, "original_price": 6500.0,
        "language": "English", "pages": 14000,
        "featured": True, "stock": 30,
        "short_desc": "The complete Srimad Bhagavatam in 18 volumes with original Sanskrit and Prabhupada's purports.",
        "description": "The complete 18-volume set includes all 12 cantos with original Sanskrit, Roman transliteration, synonyms, translations, and elaborate purports by Srila Prabhupada.",
    },
    {
        "title": "Nectar of Devotion",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 280.0, "original_price": 380.0,
        "language": "English", "pages": 534,
        "featured": True, "stock": 120,
        "short_desc": "A complete science of bhakti-yoga based on Srila Rupa Gosvami's Bhakti-rasamrta-sindhu.",
        "description": "The Nectar of Devotion describes 64 principles of devotional service, the stages of devotional development, and the ultimate perfection of loving service to Sri Krishna.",
    },
    {
        "title": "Krishna Book",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 320.0, "original_price": 450.0,
        "language": "English", "pages": 574,
        "featured": True, "stock": 90,
        "short_desc": "The Source of All Pleasure – the supreme personality of Godhead's pastimes.",
        "description": "A brilliant summary study of the Tenth Canto of Srimad Bhagavatam recounting the transcendental pastimes of Lord Sri Krishna.",
    },
    {
        "title": "Science of Self Realization",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 160.0, "original_price": 220.0,
        "language": "English", "pages": 438,
        "featured": False, "stock": 150,
        "short_desc": "Fascinating conversations between Srila Prabhupada and scientists, philosophers, and journalists.",
        "description": "A collection of conversations, essays, and lectures exploring the nature of consciousness, the self, and the Supreme.",
    },

    # ── Paper Copy — Hindi ──
    {
        "title": "Bhagavad Gita As It Is (Hindi — Hard Cover)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 300.0, "original_price": 450.0,
        "language": "Hindi", "pages": 924,
        "featured": True, "stock": 150,
        "short_desc": "सम्पूर्ण हिंदी अनुवाद श्रील प्रभुपाद के भाष्य सहित।",
        "description": "भगवद्गीता यथारूप – सम्पूर्ण मूल संस्कृत, रोमन लिप्यंतरण, शब्दार्थ, अनुवाद और श्रील प्रभुपाद के विस्तृत तात्पर्य सहित।",
    },
    {
        "title": "Nectar of Devotion (Hindi)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 260.0, "original_price": 360.0,
        "language": "Hindi", "pages": 534,
        "featured": False, "stock": 80,
        "short_desc": "भक्ति-योग का सम्पूर्ण विज्ञान हिंदी में।",
        "description": "श्रील रूप गोस्वामी की भक्ति-रसामृत-सिन्धु का सारांश अध्ययन। भक्ति सेवा के 64 सिद्धांत हिंदी में।",
    },
    {
        "title": "Krishna Book (Hindi)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 300.0, "original_price": 430.0,
        "language": "Hindi", "pages": 574,
        "featured": False, "stock": 70,
        "short_desc": "भगवान श्री कृष्ण की दिव्य लीलाएं हिंदी में।",
        "description": "श्रीमद्भागवतम के दशम स्कंध का सारांश अध्ययन — भगवान श्री कृष्ण की बाल लीलाएं, युवावस्था और दिव्य कार्य।",
    },

    # ── Paper Copy — Gujarati ──
    {
        "title": "Bhagavad Gita As It Is (Gujarati — Hard Cover)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 300.0, "original_price": 450.0,
        "language": "Gujarati", "pages": 924,
        "featured": True, "stock": 150,
        "short_desc": "સંપૂર્ણ ગુજરાતી અનુવાદ શ્રીલ પ્રભુપાદના ભાષ્ય સાથે।",
        "description": "ભગવદ્ ગીતા યથારૂપ – સંપૂર્ણ મૂળ સંસ્કૃત, રોમન લિપ્યંતરણ, શબ્દાર્થ, અનુવાદ અને શ્રીલ પ્રભુપાદના વિસ્તૃત તાત્પર્ય સાથે।",
    },
    {
        "title": "Krishna Book (Gujarati)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "paper-copy",
        "price": 300.0, "original_price": 430.0,
        "language": "Gujarati", "pages": 574,
        "featured": False, "stock": 70,
        "short_desc": "ભગવાન શ્રી કૃષ્ણની દિવ્ય લીલાઓ ગુજરાતીમાં।",
        "description": "શ્રીમદ્ ભાગવતમ્ના દશમ સ્કંધનો સારાંશ અભ્યાસ — ભગવાન શ્રી કૃષ્ણની બાળ લીલાઓ, યૌવન અને દિવ્ય કાર્યો ગુજરાતીમાં।",
    },

    # ── E-Book — English ──
    {
        "title": "Bhagavad Gita As It Is (eBook — English)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "e-book",
        "price": 99.0, "original_price": 150.0,
        "language": "English", "pages": 924,
        "featured": True, "stock": 9999,
        "is_ebook": True,
        "short_desc": "Complete authorized digital edition — instant download PDF.",
        "description": "The complete Bhagavad Gita As It Is in digital format. Includes original Sanskrit, transliteration, word-for-word synonyms, translation, and purports by Srila Prabhupada. Instant PDF download.",
    },
    {
        "title": "Nectar of Devotion (eBook — English)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "e-book",
        "price": 79.0, "original_price": 120.0,
        "language": "English", "pages": 534,
        "featured": False, "stock": 9999,
        "is_ebook": True,
        "short_desc": "Complete science of bhakti-yoga — instant PDF download.",
        "description": "Digital edition of the Nectar of Devotion. Instant PDF download after purchase.",
    },

    # ── E-Book — Hindi ──
    {
        "title": "Bhagavad Gita As It Is (eBook — Hindi)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "e-book",
        "price": 79.0, "original_price": 120.0,
        "language": "Hindi", "pages": 924,
        "featured": True, "stock": 9999,
        "is_ebook": True,
        "short_desc": "हिंदी ई-पुस्तक – तुरंत PDF डाउनलोड।",
        "description": "भगवद्गीता यथारूप का डिजिटल संस्करण हिंदी में। खरीद के बाद तुरंत PDF डाउनलोड।",
    },

    # ── E-Book — Gujarati ──
    {
        "title": "Bhagavad Gita As It Is (eBook — Gujarati)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "e-book",
        "price": 79.0, "original_price": 120.0,
        "language": "Gujarati", "pages": 924,
        "featured": True, "stock": 9999,
        "is_ebook": True,
        "short_desc": "ગુજરાતી ઈ-બુક – તાત્કાલિક PDF ડાઉનલોડ।",
        "description": "ભગવદ્ ગીતા યથારૂપ ડિજિટલ આવૃત્તિ ગુજરાતીમાં। ખરીદી પછી તાત્કાલિક PDF ડાઉનલોડ।",
    },
]


COUPONS = [
    {
        "code": "HARE10",
        "description": "10% off on all orders",
        "discount_type": "percent",
        "discount_value": 10,
        "min_order": 200,
        "max_discount": 200,
        "max_uses": 500,
    },
    {
        "code": "KRISHNA50",
        "description": "Flat ₹50 off on orders above ₹500",
        "discount_type": "fixed",
        "discount_value": 50,
        "min_order": 500,
        "max_uses": 1000,
    },
    {
        "code": "WELCOME20",
        "description": "20% off for first-time buyers",
        "discount_type": "percent",
        "discount_value": 20,
        "min_order": 300,
        "max_discount": 300,
        "max_uses": 200,
    },
]


def seed():
    with app.app_context():
        db.create_all()

        # Skip if already seeded
        if Category.query.count() > 0:
            print("[SKIP] Database already seeded. Skipping.")
            return

        print("[SEED] Seeding categories...")
        cat_map = {}
        for cat_data in CATEGORIES:
            cat = Category(**cat_data)
            db.session.add(cat)
            db.session.flush()
            cat_map[cat_data["slug"]] = cat.id
        db.session.commit()

        print("[SEED] Seeding books...")
        for book_data in BOOKS:
            slug     = book_data.pop("category")
            cat_id   = cat_map.get(slug)
            isbn_val = f"978{hash(book_data['title']) % 10**10:010d}"
            book = Book(
                **book_data,
                category_id = cat_id,
                isbn        = isbn_val,
                publisher   = "The Bhaktivedanta Book Trust",
            )
            db.session.add(book)
        db.session.commit()

        print("[SEED] Seeding coupons...")
        for coup_data in COUPONS:
            coupon = Coupon(**coup_data, active=True)
            db.session.add(coupon)
        db.session.commit()

        print("\n[OK] Seeding complete!")
        print(f"   Categories : {Category.query.count()}")
        print(f"   Books      : {Book.query.count()}")
        print(f"   Coupons    : {Coupon.query.count()}")
        print(f"\n[ADMIN] Login -> Username: admin | Password: Hare@Krishna108")
        print(f"[COUPONS] Sample Coupons -> HARE10, KRISHNA50, WELCOME20\n")


if __name__ == "__main__":
    seed()
