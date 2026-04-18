"""
import_bbt_books.py
-------------------
Bulk-imports BBT books from the official price list into the ISKCON Book Store.
Each book is inserted once per language variant (English / Hindi / Gujarati).
Skips any title + language combination that already exists.

Run:  python import_bbt_books.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, Book, Category

AUTHOR    = "A.C. Bhaktivedanta Swami Prabhupada"
PUBLISHER = "The Bhaktivedanta Book Trust"

# ─────────────────────────────────────────────────────────────────────────────
# Book data
# Each entry: (title, {lang: price | None}, short_desc, full_desc)
# Price None = not available in that language → skip
# ─────────────────────────────────────────────────────────────────────────────
BOOKS = [
    (
        "Bhagavad Gita As It Is",
        {"English": 300, "Hindi": 225, "Gujarati": 250},
        "The complete authorized edition with original Sanskrit, transliteration, word-for-word translation, and elaborate purports.",
        (
            "A clear and authoritative presentation of life's ultimate purpose — understanding "
            "one's eternal relationship with Lord Krishna, the Supreme Personality of Godhead. "
            "The book explains that while various paths such as karma (action), jñāna (knowledge), "
            "and dhyāna (meditation) are described, they reach perfection only when centered on "
            "devotion to Krishna. It establishes that true wisdom is not merely intellectual or "
            "ritualistic, but realized through surrender and loving service to God."
        ),
    ),
    (
        "Bhagavad Gita Pocket",
        {"English": 200, "Hindi": 200, "Gujarati": 175},
        "A compact version of the Bhagavad Gita — ideal for daily reflection and beginners.",
        (
            "A compact version of the Bhagavad Gita for quick reading. Ideal for daily reflection "
            "and beginners. Contains essential teachings in a simplified format."
        ),
    ),
    (
        "Krishna Book",
        {"English": 300, "Hindi": 275, "Gujarati": 275},
        "A devotional summary of the Tenth Canto of Srimad Bhagavatam — the divine pastimes of Lord Krishna.",
        (
            "Krsna: The Supreme Personality of Godhead is a devotional summary of the Tenth Canto "
            "of the Śrīmad Bhāgavatam, focusing on the divine pastimes of Lord Krishna — from His "
            "miraculous birth in Mathura and childhood in Vrindavan to His role as a prince in "
            "Dwaraka. Prabhupada presents Krishna as the Supreme Personality of Godhead, emphasizing "
            "devotion (bhakti) as the highest spiritual path."
        ),
    ),
    (
        "Srimad Bhagavatam (Set of 18 Volumes)",
        {"English": 9000, "Hindi": 7000, "Gujarati": 7500},
        "A multi-volume scripture covering creation, avatars, and devotion — the cream of all Vedic literature.",
        (
            "A multi-volume scripture covering creation, avatars, and devotion. Emphasizes pure love "
            "for God as the highest goal. Includes deep philosophical and spiritual teachings across "
            "12 cantos, from the questions of the sages (Canto 1) to the life and pastimes of Lord "
            "Krishna (Canto 10) and the conclusion of Kali Yuga (Canto 12)."
        ),
    ),
    (
        "Chaitanya Charitamrit (Set of 9 Books)",
        {"English": 3500, "Hindi": 4000, "Gujarati": 4000},
        "The life and teachings of Chaitanya Mahaprabhu in 3 parts — Adi, Madhya, and Antya Lila.",
        (
            "Details the life of Chaitanya Mahaprabhu across three lilas (Adi, Madhya, Antya). "
            "Teaches the power of chanting and devotion and explains the philosophy of divine love "
            "(Gaudiya Vaishnava philosophy). Reveals the highest stage of devotion and separation "
            "from Krishna."
        ),
    ),
    (
        "Finding Our Lost Happiness",
        {"English": 80, "Hindi": 80, "Gujarati": 80},
        "A simple introduction to spiritual life — how true happiness is found through Krishna consciousness.",
        (
            "A simple and inspiring introduction to spiritual life, revealing how true happiness is "
            "found by reconnecting with our eternal relationship with Lord Krishna. Explains that "
            "material achievements alone cannot satisfy the soul, and that lasting happiness comes "
            "from within through spiritual awareness and devotion."
        ),
    ),
    (
        "Life Comes from Life",
        {"English": 70, "Hindi": 70, "Gujarati": 70},
        "A thought-provoking exploration proving that life arises from life, not from matter.",
        (
            "A thought-provoking exploration of the origin of life, presenting the conclusion that "
            "life arises from life — not from matter. Through conversations between Srila Prabhupada "
            "and scientists, the book challenges the idea that chemicals alone can produce living "
            "beings. Establishes that consciousness is the fundamental principle of life."
        ),
    ),
    (
        "Science of Self Realization",
        {"English": 125, "Hindi": 125, "Gujarati": 125},
        "A compelling presentation of spiritual knowledge — the true nature of the self beyond body and mind.",
        (
            "A compelling presentation of spiritual knowledge, explaining the true nature of the self "
            "beyond the body and mind. Reveals that real identity lies in the soul, which is eternal "
            "and full of knowledge and bliss. Presents Krishna consciousness as a scientific and "
            "practical process for awakening higher awareness."
        ),
    ),
    (
        "Nectar of Devotion",
        {"English": 190, "Hindi": 190, "Gujarati": 190},
        "A systematic guide to bhakti-yoga — the science of devotional service to Lord Krishna.",
        (
            "A systematic and profound guide to the practice of bhakti-yoga, explaining the science "
            "of devotional service to Lord Krishna. Based on ancient Vedic teachings, the book "
            "outlines the stages and principles of pure devotion. Presents bhakti as both the means "
            "and the goal of spiritual life, accessible to anyone regardless of background."
        ),
    ),
    (
        "Teachings of Lord Chaitanya",
        {"English": 150, "Hindi": 150, "Gujarati": 150},
        "A deep presentation of the life and teachings of Chaitanya Mahaprabhu and Gaudiya Vaishnava philosophy.",
        (
            "A deep and authoritative presentation of the life and teachings of Chaitanya Mahaprabhu, "
            "revealing the essence of Gaudiya Vaishnava philosophy. Establishes that the highest "
            "spiritual goal is pure love of Lord Krishna, achieved through the congregational chanting "
            "of the holy names (sankirtana)."
        ),
    ),
    (
        "Teachings of Lord Kapila",
        {"English": 100, "Hindi": 100, "Gujarati": 100},
        "Transcendental knowledge spoken by Lord Kapila to His mother Devahuti — the science of liberation.",
        (
            "A clear and profound presentation of transcendental knowledge spoken by Lord Kapila to "
            "His mother Devahūti. Based on the Śrīmad Bhāgavatam, explains the science of "
            "self-realization and liberation from material bondage through Sāṅkhya-yoga as the means "
            "to understand Lord Krishna as the ultimate cause of everything."
        ),
    ),
    (
        "Teachings of Queen Kunti",
        {"English": 90, "Hindi": 90, "Gujarati": 90},
        "The profound prayers and instructions of Queen Kunti — wisdom revealed through great suffering.",
        (
            "A heartfelt presentation of the profound prayers and instructions of Queen Kunti. Based "
            "on prayers in the Śrīmad Bhāgavatam, reveals deep spiritual wisdom expressed during "
            "moments of great suffering. Establishes that true devotion is revealed through humility, "
            "dependence on God, and unwavering faith even in adversity."
        ),
    ),
    (
        "The Matchless Gift",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A priceless spiritual treasure — introducing the chanting process as the easiest path to self-realization.",
        (
            "A priceless spiritual treasure that awakens inner wisdom and guides the soul toward "
            "lasting peace and devotion. Explains that spiritual realization in the present age is "
            "most effectively achieved through the congregational chanting (sankirtana) process, "
            "which purifies the heart and awakens dormant love for God."
        ),
    ),
    (
        "Beyond Birth and Death",
        {"English": 25, "Hindi": 25, "Gujarati": 25},
        "A concise presentation of the eternal soul — life does not end with the death of the body.",
        (
            "A concise and powerful presentation of the eternal nature of the soul, explaining that "
            "life does not end with the death of the body. Draws from the Bhagavad Gita and Śrīmad "
            "Bhāgavatam to reveal the science of transmigration and liberation. Presents Krishna "
            "consciousness as the process to transcend the cycle of birth and death."
        ),
    ),
    (
        "Introduction to Bhagavad Gita",
        {"English": 25, "Hindi": 25, "Gujarati": 25},
        "A simple overview of Gita teachings — perfect for first-time readers.",
        (
            "A simple overview of Bhagavad Gita teachings. Perfect for first-time readers. Explains "
            "key concepts clearly and introduces the essence of Vedic spiritual knowledge in an "
            "accessible format."
        ),
    ),
    (
        "Krsna – The Reservoir of Pleasure",
        {"English": 25, "Hindi": 25, "Gujarati": 25},
        "Lord Krishna as the ultimate source of all happiness — real joy is found in connection with Him.",
        (
            "A devotional presentation describing Lord Krishna as the ultimate source of all happiness "
            "and spiritual joy. Explains that all beings are naturally seeking pleasure, but real and "
            "lasting happiness is found only in relationship with Krishna. Material pleasures are "
            "temporary reflections of the original spiritual pleasure found in Krishna."
        ),
    ),
    (
        "The Nectar of Instruction",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A concise practical guide to the essential principles of devotional life and steady spiritual progress.",
        (
            "A concise and practical guide to the essential principles of devotional life, explaining "
            "how to progress steadily in bhakti-yoga toward pure love of Lord Krishna. Outlines clear "
            "instructions for spiritual advancement including controlled senses, regulated behavior, "
            "and sincere association with devotees."
        ),
    ),
    (
        "Bhakti – The Art of Eternal Love",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A presentation of the eternal relationship between the soul and Lord Krishna — devotion as natural function.",
        (
            "A simple and inspiring presentation of the eternal relationship between the soul and Lord "
            "Krishna, explaining bhakti as the natural and original function of every living being. "
            "Presents bhakti-yoga as the highest expression of love, beyond material attraction and "
            "temporary relationships."
        ),
    ),
    (
        "Civilization and Transcendence",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A critical examination of modern material civilization contrasted with the Vedic vision of spiritual progress.",
        (
            "A critical examination of modern material civilization contrasted with the Vedic vision "
            "of spiritual progress. Questions whether technological and economic advancement alone can "
            "be considered true civilization. Explains that a civilization focused only on bodily "
            "comfort ignores the eternal identity of the soul."
        ),
    ),
    (
        "On the Way to Krsna",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A practical guide for beginners — how to gradually progress toward loving devotion to Lord Krishna.",
        (
            "A practical and encouraging guide for beginners on the spiritual journey, explaining how "
            "to gradually progress toward the ultimate goal of loving devotion to Lord Krishna. "
            "Presents simple principles of Krishna consciousness in everyday life — chanting, hearing, "
            "and remembering Krishna."
        ),
    ),
    (
        "Vedic Perspective in Modern Times",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "Vedic wisdom applied to contemporary life — timeless spiritual insights for the modern world.",
        (
            "Vedic wisdom applied to contemporary life. Presents timeless spiritual insights from "
            "the Vedic tradition for the modern world, helping readers understand how ancient "
            "knowledge remains fully relevant to today's challenges and questions."
        ),
    ),
    (
        "Sri Ishopanishad",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "One of the most important Upanishads — 18 mantras revealing the complete picture of the Absolute Truth.",
        (
            "One of the most important Upanishads, containing 18 mantras that reveal the complete "
            "picture of the Absolute Truth. With translation and purports by Srila Prabhupada, it "
            "establishes that everything belongs to the Supreme Lord and teaches how to live in "
            "harmony with this spiritual truth."
        ),
    ),
    (
        "Perfect Questions, Perfect Answers",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A candid conversation between Srila Prabhupada and a young American seeker on spiritual life.",
        (
            "A candid and illuminating conversation between Srila Prabhupada and Bob Cohen, a young "
            "American Peace Corps worker. Covers essential questions about spiritual life, God, "
            "consciousness, and the path to lasting happiness in a direct and accessible manner."
        ),
    ),
    (
        "Message of Godhead",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "An early work by Srila Prabhupada introducing Bhagavad Gita wisdom to a Western audience.",
        (
            "An early work by Srila Prabhupada introducing the wisdom of the Bhagavad Gita to a "
            "Western audience. Presents the essential message of Godhead — our eternal relationship "
            "with the Supreme — in a clear and accessible format."
        ),
    ),
    (
        "Transcendental Teachings of Prahlada Maharaja",
        {"English": 25, "Hindi": 25, "Gujarati": 25},
        "The teachings of Prahlada Maharaja — a young devotee who showed pure devotion to Lord Vishnu.",
        (
            "Presents the teachings of Prahlada Maharaja, a young devotee who showed unwavering "
            "devotion to Lord Vishnu even in the face of great opposition. Based on the Srimad "
            "Bhagavatam, these teachings reveal the power of pure devotion and surrender to God."
        ),
    ),
    (
        "The Laws of Nature",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "An infallible justice — how the laws of karma govern all living beings.",
        (
            "An exploration of the laws of nature from a Vedic perspective, explaining how karma "
            "and the infallible justice of nature govern all living beings. Shows how understanding "
            "these laws leads to spiritual advancement and freedom from material suffering."
        ),
    ),
    (
        "Spiritual Yoga",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "The yoga of devotion — the highest form of yoga connecting the soul with the Supreme.",
        (
            "Explores the spiritual dimensions of yoga beyond physical practice, explaining that the "
            "highest form of yoga is devotional service (bhakti-yoga) which connects the soul "
            "directly with the Supreme Lord Krishna. Based on the teachings of Srila Prabhupada."
        ),
    ),
    (
        "Easy Journey to Other Planets",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A scientific and Vedic exploration of consciousness — travelling beyond the material universe.",
        (
            "A scientific and Vedic exploration of consciousness, explaining that there are other "
            "planets and realms beyond the material universe that can be reached through spiritual "
            "practice. Presents the ancient Vedic understanding of the cosmos and the soul's journey."
        ),
    ),
    (
        "Srila Prabhupada Lilamrita",
        {"English": 1400, "Hindi": 1400, "Gujarati": None},
        "The authorized biography of Srila Prabhupada — a life of extraordinary spiritual achievement.",
        (
            "The authorized biography of A.C. Bhaktivedanta Swami Prabhupada, compiled by Satsvarupa "
            "dasa Goswami. Chronicles his extraordinary life — from birth in Calcutta in 1896 to "
            "founding ISKCON in New York in 1966 and establishing Krishna consciousness worldwide. "
            "An inspiring account of surrender, perseverance, and divine grace."
        ),
    ),
    (
        "Rajavidhya – The King of Knowledge",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "The king of all knowledge — understanding the supreme science of devotion to Krishna.",
        (
            "Based on Chapter 9 of the Bhagavad Gita, presents the supreme science of devotional "
            "service as the king of all knowledge and the king of all secrets. Explains why bhakti "
            "is the most direct and joyful path to Krishna and liberation."
        ),
    ),
    (
        "The Path of Perfection",
        {"English": 70, "Hindi": 70, "Gujarati": 70},
        "Yoga for the modern age — the path to spiritual perfection through the Bhagavad Gita.",
        (
            "Explores the path to spiritual perfection through the yoga system described in the "
            "Bhagavad Gita. Explains how to practice yoga in the modern age in a way that is "
            "practical and leads to the highest goal — pure love of God."
        ),
    ),
    (
        "The Perfection of Yoga",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "Where does yoga ultimately lead? The perfection of all yoga is bhakti — devotion to Krishna.",
        (
            "Explains the ultimate goal of all yoga systems, showing that the perfection of yoga "
            "is bhakti — loving devotion to Lord Krishna. Based on the sixth chapter of the Bhagavad "
            "Gita, presents a clear and practical understanding of yoga's highest destination."
        ),
    ),
    (
        "Elevation to Krishna Consciousness",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "How to elevate consciousness from material to spiritual awareness — the process of Krishna consciousness.",
        (
            "Explains the process of elevating human consciousness from the material to the spiritual "
            "platform through Krishna consciousness. Covers the principles of bhakti, the importance "
            "of chanting, regulated spiritual practice, and the goal of pure love for God."
        ),
    ),
    (
        "A Second Chance",
        {"English": 65, "Hindi": 65, "Gujarati": 65},
        "The story of a near-death experience — Ajamila and the power of the holy name at the moment of death.",
        (
            "The story of Ajamila from the Sixth Canto of Srimad Bhagavatam — a man who despite a "
            "sinful life was saved at the moment of death by accidentally chanting the name of God. "
            "A powerful teaching on the extraordinary power of the holy name and the possibility of "
            "spiritual redemption at any stage of life."
        ),
    ),
    (
        "Dharma – The Way of Transcendence",
        {"English": 50, "Hindi": 50, "Gujarati": 50},
        "What is dharma? The true meaning of duty — beyond religion to the eternal function of the soul.",
        (
            "Explores the true meaning of dharma beyond religious ritual or social duty, revealing "
            "it as the eternal function of the soul — to serve and love the Supreme Lord. Based on "
            "the teachings of Srila Prabhupada, presents dharma as the path of transcendence."
        ),
    ),
    (
        "The Journey of Self Discovery",
        {"English": 120, "Hindi": 120, "Gujarati": 120},
        "Articles and conversations by Srila Prabhupada on spiritual topics — science, yoga, and Krishna consciousness.",
        (
            "A collection of enlightening articles and conversations by Srila Prabhupada covering "
            "topics such as the science of self-realization, yoga, meditation, consciousness, and "
            "Krishna consciousness. Ideal for readers new to Vedic philosophy seeking a broad "
            "introduction to spiritual life."
        ),
    ),
    (
        "The Quest for Enlightenment",
        {"English": 100, "Hindi": 100, "Gujarati": 100},
        "Conversations and articles exploring the quest for spiritual enlightenment and the nature of consciousness.",
        (
            "Conversations and articles by Srila Prabhupada exploring the universal quest for "
            "enlightenment and the nature of consciousness. Addresses the fundamental questions "
            "of existence and presents the Vedic answers to humanity's deepest spiritual longings."
        ),
    ),
    (
        "Beyond Illusion and Doubt",
        {"English": 65, "Hindi": 65, "Gujarati": 65},
        "Srila Prabhupada responds to Western philosophers — from Descartes to Darwin and beyond.",
        (
            "Srila Prabhupada responds to the ideas of great Western philosophers including Descartes, "
            "Darwin, Freud, and Marx, showing how Vedic wisdom addresses and surpasses the "
            "speculations of Western thought. A fascinating dialogue between Eastern and Western "
            "philosophical traditions."
        ),
    ),
    (
        "Krishna Consciousness – The Topmost Yoga System",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "Why bhakti-yoga is the topmost of all yoga systems — the supreme process for the present age.",
        (
            "Explains why bhakti-yoga — devotional service to Lord Krishna — is the topmost of all "
            "yoga systems. Shows that in the present age of Kali, the chanting of the holy names "
            "is the most effective, powerful, and accessible process for spiritual advancement."
        ),
    ),
    (
        "Hare Krishna Challenge",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "A challenge to skeptics — presenting the Hare Krishna philosophy to modern questioners.",
        (
            "Presents the Hare Krishna philosophy in response to skeptical questions and challenges "
            "from modern thinkers. A clear and direct presentation of Krishna consciousness that "
            "addresses doubts and misconceptions, showing the rational and spiritual basis of the "
            "Hare Krishna movement."
        ),
    ),
    (
        "Selected Verses from Scriptures",
        {"English": 190, "Hindi": 190, "Gujarati": None},
        "A collection of essential verses from Vedic scriptures with translations and commentary.",
        (
            "A carefully curated collection of essential verses from major Vedic scriptures including "
            "the Bhagavad Gita, Srimad Bhagavatam, and Upanishads. With translations and explanatory "
            "commentary, this is a valuable reference for students and practitioners of Vedic knowledge."
        ),
    ),
    (
        "Coming Back",
        {"English": 40, "Hindi": 40, "Gujarati": 40},
        "The science of reincarnation — compelling evidence for the transmigration of the soul.",
        (
            "Presents compelling evidence for the transmigration of the soul (reincarnation) from "
            "both Vedic and modern scientific perspectives. Includes documented cases, interviews, "
            "and the Vedic explanation of how consciousness continues beyond the death of the body. "
            "Explains how to break free from the cycle of birth and death through Krishna consciousness."
        ),
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
def get_or_create_category(slug):
    """Return the paper-copy category id (create if missing)."""
    cat = Category.query.filter_by(slug=slug).first()
    if not cat:
        cat = Category(
            name="Paper Copy",
            slug="paper-copy",
            icon="📗",
            sort_order=1,
            description="Physical books in English, Hindi & Gujarati by Srila Prabhupada",
        )
        db.session.add(cat)
        db.session.flush()
        print(f"  [CREATE] Category 'Paper Copy' created.")
    return cat.id


def run_import():
    with app.app_context():
        cat_id = get_or_create_category("paper-copy")

        inserted = 0
        skipped  = 0

        for title, prices, short_desc, full_desc in BOOKS:
            for lang, price in prices.items():
                if price is None:
                    print(f"  [SKIP]   {title} ({lang}) — not available")
                    skipped += 1
                    continue

                # Check for duplicate
                existing = Book.query.filter_by(title=title, language=lang).first()
                if existing:
                    print(f"  [EXISTS] {title} ({lang}) — already in DB (id={existing.id})")
                    skipped += 1
                    continue

                book = Book(
                    title          = title,
                    author         = AUTHOR,
                    description    = full_desc,
                    short_desc     = short_desc,
                    price          = float(price),
                    original_price = None,
                    language       = lang,
                    publisher      = PUBLISHER,
                    category_id    = cat_id,
                    stock          = 100,
                    featured       = False,
                    active         = True,
                )
                db.session.add(book)
                print(f"  [ADD]    {title} ({lang}) -- Rs.{price}")
                inserted += 1

        db.session.commit()
        print(f"\nDone! Inserted: {inserted}  |  Skipped/Existing: {skipped}")


if __name__ == "__main__":
    run_import()
