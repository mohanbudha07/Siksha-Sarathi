def get_subject(question):
    question = question.lower()

    subjects = {
        "Science": [
    "cell",
    "plant",
    "animal",
    "physics",
    "chemical",
    "biology",
    "energy",
    "photosynthesis",
    "respiration",
    "ecosystem",
    "force",
    "motion"
],

        "Mathematics": [
            "solve", "equation", "algebra",
            "number", "calculate", "percentage"
        ],

        "English": [
            "grammar", "noun", "verb",
            "sentence", "meaning"
        ],

        "Social Studies": [
            "history", "government",
            "democracy", "culture"
        ],

        "Nepali": [
            "munamadan", "nepali",
            "kabi", "sahitya"
        ]
    }

    for subject, words in subjects.items():
        for word in words:
            if word in question:
                return subject

    return "General"


def generate_answer(question):

    subject = get_subject(question)

    question = question.lower()

    knowledge = {

        "photosynthesis":
        "Photosynthesis is the process where green plants prepare food using sunlight, carbon dioxide and water.",

        "cell":
        "A cell is the basic structural and functional unit of life.",

        "democracy":
        "Democracy is a system where people choose their representatives through voting.",

        "munamadan":
        "Muna Madan is a famous Nepali epic poem written by Laxmi Prasad Devkota."
    }


    for key, value in knowledge.items():
        if key in question:
            return subject, value


    return subject, (
        "I am Siksha Sarathi AI Assistant. "
        "I can help you with secondary level subjects. "
        "Please ask a specific question."
    )