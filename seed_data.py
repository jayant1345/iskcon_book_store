"""
Seed database with ISKCON categories and books.
Run: python seed_data.py
"""

from app import app, db, Category, Book, Coupon
from datetime import datetime, timedelta


CATEGORIES = [
    {"name": "Bhagavad Gita",         "slug": "bhagavad-gita",         "icon": "📖", "sort_order": 1,
     "description": "The Song of God – timeless wisdom spoken by Lord Krishna"},
    {"name": "Srimad Bhagavatam",     "slug": "srimad-bhagavatam",     "icon": "📚", "sort_order": 2,
     "description": "The great scripture on the science of God"},
    {"name": "Chaitanya Charitamrita","slug": "chaitanya-charitamrita", "icon": "🌸", "sort_order": 3,
     "description": "Life and teachings of Sri Chaitanya Mahaprabhu"},
    {"name": "Philosophy & Science",  "slug": "philosophy-science",     "icon": "🔬", "sort_order": 4,
     "description": "Vedic philosophy and its intersection with modern science"},
    {"name": "Devotional Guides",     "slug": "devotional-guides",      "icon": "🙏", "sort_order": 5,
     "description": "Practical guides for devotional service"},
    {"name": "Children's Books",      "slug": "childrens-books",        "icon": "🎨", "sort_order": 6,
     "description": "Krishna consciousness for young readers"},
    {"name": "Hindi Books",           "slug": "hindi-books",            "icon": "🇮🇳", "sort_order": 7,
     "description": "ISKCON books in Hindi"},
    {"name": "Sets & Collections",    "slug": "sets-collections",       "icon": "📦", "sort_order": 8,
     "description": "Complete sets and special collections"},
]


BOOKS = [
    # ── Bhagavad Gita ──
    {
        "title": "Bhagavad Gita As It Is (Large, Hard Cover)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "bhagavad-gita",
        "price": 350.0, "original_price": 550.0,
        "language": "English", "pages": 924,
        "featured": True, "stock": 200,
        "short_desc": "The complete authorized edition with original Sanskrit, transliteration, word-for-word translation, and elaborate purports.",
        "description": """The Bhagavad-gita is universally renowned as the jewel of India's spiritual wisdom. Spoken by the Supreme Personality of Godhead, Lord Sri Krishna, to His intimate disciple Arjuna, the Gita's seven hundred verses provide a definitive guide to the science of self-realization.

This is the largest-selling edition of the Gita in the Western world. As a genuine representation of Indian culture, it presents the original Sanskrit text, its Roman transliteration, word-for-word synonyms, translation, and elaborate purports by Srila Prabhupada — one of the greatest scholars and devotees of Lord Krishna of our time.""",
    },
    {
        "title": "Bhagavad Gita As It Is (Pocket Size)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "bhagavad-gita",
        "price": 110.0, "original_price": 150.0,
        "language": "English", "pages": 924,
        "featured": False, "stock": 500,
        "short_desc": "Compact pocket edition – perfect for on-the-go reading.",
        "description": "Same complete authorized translation in a convenient pocket size. Includes all 700 verses with purports by Srila Prabhupada.",
    },
    {
        "title": "Bhagavad Gita As It Is (Hindi)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "hindi-books",
        "price": 300.0, "original_price": 450.0,
        "language": "Hindi", "pages": 924,
        "featured": True, "stock": 150,
        "short_desc": "सम्पूर्ण हिंदी अनुवाद श्रील प्रभुपाद के भाष्य सहित।",
        "description": "भगवद्गीता यथारूप – सम्पूर्ण मूल संस्कृत, रोमन लिप्यंतरण, शब्दार्थ, अनुवाद और श्रील प्रभुपाद के विस्तृत तात्पर्य सहित।",
    },

    # ── Srimad Bhagavatam ──
    {
        "title": "Srimad Bhagavatam – Complete 18-Volume Set",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "sets-collections",
        "price": 4500.0, "original_price": 6500.0,
        "language": "English", "pages": 14000,
        "featured": True, "stock": 30,
        "short_desc": "The complete Srimad Bhagavatam in 18 volumes with original Sanskrit and Prabhupada's purports.",
        "description": """The Srimad Bhagavatam (Bhagavata Purana) is the spotless Purana. It is especially meant for those who desire to get out of the entanglement of activities and their reactions.

This complete 18-volume set includes all 12 cantos with original Sanskrit, Roman transliteration, synonyms, translations, and elaborate purports by His Divine Grace A.C. Bhaktivedanta Swami Prabhupada.""",
    },
    {
        "title": "Srimad Bhagavatam – Canto 1 (3 Volumes)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "srimad-bhagavatam",
        "price": 800.0, "original_price": 1100.0,
        "language": "English", "pages": 1200,
        "featured": False, "stock": 80,
        "short_desc": "The First Canto: Creation – 3 volume set.",
        "description": "The First Canto of the Srimad Bhagavatam in three volumes. Covers the creation, the dynasties of the patriarchs, and introduces the universal form of the Lord.",
    },

    # ── Chaitanya Charitamrita ──
    {
        "title": "Sri Chaitanya Charitamrita – Complete 17-Volume Set",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "sets-collections",
        "price": 3800.0, "original_price": 5500.0,
        "language": "English", "pages": 11000,
        "featured": False, "stock": 20,
        "short_desc": "Life and teachings of Sri Chaitanya Mahaprabhu in 17 volumes.",
        "description": "Sri Chaitanya Charitamrita is the biography and philosophy of Sri Chaitanya Mahaprabhu, who introduced the worldwide sankirtana movement 500 years ago.",
    },
    {
        "title": "Sri Chaitanya Charitamrita – Adi-lila (4 Volumes)",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "chaitanya-charitamrita",
        "price": 1200.0, "original_price": 1600.0,
        "language": "English", "pages": 2500,
        "featured": False, "stock": 45,
        "short_desc": "The early life of Lord Chaitanya – 4 volume set.",
        "description": "The Adi-lila (early pastimes) of Sri Chaitanya Mahaprabhu, covering his divine childhood, youth, and the beginnings of the sankirtana movement.",
    },

    # ── Philosophy & Science ──
    {
        "title": "Nectar of Devotion",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "philosophy-science",
        "price": 280.0, "original_price": 380.0,
        "language": "English", "pages": 534,
        "featured": True, "stock": 120,
        "short_desc": "A complete science of bhakti-yoga based on Srila Rupa Gosvami's Bhakti-rasamrta-sindhu.",
        "description": """The Nectar of Devotion is the summary study of Srila Rupa Gosvami's Bhakti-rasamrta-sindhu, the standard textbook on pure devotional service.

This book describes 64 principles of devotional service, the stages of devotional development, and the ultimate perfection of loving service to Sri Krishna.""",
    },
    {
        "title": "Nectar of Instruction",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "devotional-guides",
        "price": 95.0, "original_price": 130.0,
        "language": "English", "pages": 168,
        "featured": False, "stock": 200,
        "short_desc": "Eleven concise instructions for beginning and advancing in devotional service.",
        "description": "The Nectar of Instruction (Upadeshamrita) by Srila Rupa Gosvami contains eleven essential verses for devotees of Lord Krishna. This small but important book provides the key to spiritual advancement.",
    },
    {
        "title": "Science of Self Realization",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "philosophy-science",
        "price": 160.0, "original_price": 220.0,
        "language": "English", "pages": 438,
        "featured": True, "stock": 150,
        "short_desc": "Fascinating conversations between Srila Prabhupada and scientists, philosophers, and journalists.",
        "description": "A collection of conversations, essays, and lectures by Srila Prabhupada that explore the nature of consciousness, the self, and the Supreme. Includes dialogues with scientists at MIT, Oxford, and the Soviet Academy of Sciences.",
    },
    {
        "title": "Perfect Questions, Perfect Answers",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "philosophy-science",
        "price": 85.0, "original_price": 120.0,
        "language": "English", "pages": 124,
        "featured": False, "stock": 180,
        "short_desc": "Profound conversations between Srila Prabhupada and a young American student.",
        "description": "A series of candid, engaging conversations between Srila Prabhupada and Bob Cohen, a young Peace Corps worker, that cut to the heart of the world's most important questions.",
    },
    {
        "title": "Easy Journey to Other Planets",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "philosophy-science",
        "price": 70.0, "original_price": 100.0,
        "language": "English", "pages": 96,
        "featured": False, "stock": 200,
        "short_desc": "Transfer of consciousness and the science of antimatter according to Vedic knowledge.",
        "description": "One of Srila Prabhupada's earliest books, discussing the possibility of transferring one's consciousness from the material to the spiritual planets.",
    },
    {
        "title": "Beyond Birth and Death",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "philosophy-science",
        "price": 75.0, "original_price": 100.0,
        "language": "English", "pages": 96,
        "featured": False, "stock": 180,
        "short_desc": "The soul's journey beyond the cycle of birth and death.",
        "description": "Through the timeless teachings of the Bhagavad-gita, Srila Prabhupada here shows how we can make our current life our last — and attain a state of eternal bliss.",
    },

    # ── Devotional Guides ──
    {
        "title": "Krishna Book",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "devotional-guides",
        "price": 320.0, "original_price": 450.0,
        "language": "English", "pages": 574,
        "featured": True, "stock": 90,
        "short_desc": "The Source of All Pleasure – the supreme personality of Godhead's pastimes.",
        "description": """Krsna, the Supreme Personality of Godhead is a brilliant summary study of the Tenth Canto of Srimad Bhagavatam.

This beautiful book recounts the transcendental pastimes of Lord Sri Krishna — His appearance, childhood, youth, and the battles He fought to protect His devotees. Reading about Krishna's activities purifies the heart and elevates one to spiritual consciousness.""",
    },
    {
        "title": "Raja Vidya: The King of Knowledge",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "devotional-guides",
        "price": 120.0, "original_price": 160.0,
        "language": "English", "pages": 152,
        "featured": False, "stock": 140,
        "short_desc": "Based on the ninth chapter of Bhagavad Gita — the supreme confidential knowledge.",
        "description": "Raja Vidya is based on lectures given by Srila Prabhupada on the ninth chapter of Bhagavad-gita. It describes the royal path of knowledge by which one can achieve the highest perfection.",
    },
    {
        "title": "Teachings of Lord Kapila",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "devotional-guides",
        "price": 180.0, "original_price": 250.0,
        "language": "English", "pages": 276,
        "featured": False, "stock": 110,
        "short_desc": "The philosophy of Sankhya as taught by Lord Kapila to his mother Devahuti.",
        "description": "The teachings of Lord Kapila, the son of Devahuti, as described in the Third Canto of Srimad Bhagavatam. Covers the Sankhya philosophy, bhakti-yoga, and the path to liberation.",
    },

    # ── Children's Books ──
    {
        "title": "Gopal the Cowherd Boy",
        "author": "Vishaka Devi Dasi",
        "category": "childrens-books",
        "price": 150.0, "original_price": 200.0,
        "language": "English", "pages": 64,
        "featured": False, "stock": 300,
        "short_desc": "A beautifully illustrated children's story of young Krishna and His cowherd friends.",
        "description": "A delightful, fully illustrated book for children about the childhood pastimes of Lord Krishna as a cowherd boy in Vrindavan. Perfect for ages 4-10.",
    },
    {
        "title": "Prayers of King Kulashekhara",
        "author": "A.C. Bhaktivedanta Swami Prabhupada",
        "category": "devotional-guides",
        "price": 90.0, "original_price": 120.0,
        "language": "English", "pages": 128,
        "featured": False, "stock": 120,
        "short_desc": "Nineteen beautiful prayers by the devotee-king Kulashekhara.",
        "description": "The Mukunda-mala-stotra is a garland of prayers for the lotus feet of Lord Krishna, composed by the South Indian king Kulashekhara Maharaja, a great devotee.",
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
