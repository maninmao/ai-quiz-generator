import os
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
import PyPDF2

# from nlp_utils import generate_questions
from mynlp import generate_questions



app = Flask(__name__)
app.secret_key = "dev-secret-key-change-this"  # replace before deploying

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(filepath):
    text = ""
    with open(filepath, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf_file" not in request.files:
        return render_template("index.html", error="No file was selected.")

    file = request.files["pdf_file"]

    if file.filename == "":
        return render_template("index.html", error="No file was selected.")

    if not allowed_file(file.filename):
        return render_template("index.html", error="Please upload a PDF file.")

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    text = extract_text_from_pdf(filepath)
    if not text or len(text.split()) < 20:
        return render_template(
            "index.html",
            error="Couldn't find enough readable text in that PDF. Try a text-based PDF (not a scanned image).",
        )

    questions = generate_questions(text, num_questions=10)
    if not questions:
        return render_template(
            "index.html",
            error="Couldn't generate questions from this PDF. Try a PDF with more content.",
        )

    # Store quiz state in the session
    session["quiz_title"] = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
    session["questions"] = questions
    session["answers"] = {}
    session["current"] = 0

    return redirect(url_for("quiz"))


@app.route("/quiz")
def quiz():
    questions = session.get("questions")
    if not questions:
        return redirect(url_for("home"))

    total = len(questions)
    index = request.args.get("index", session.get("current", 0), type=int)
    index = max(0, min(index, total - 1))
    session["current"] = index

    answers = session.get("answers", {})
    answered_count = len(answers)
    correct_count = sum(1 for a in answers.values() if a["correct"])
    percent = round((correct_count / answered_count) * 100, 1) if answered_count else 0

    current_question = questions[index]
    current_answer = answers.get(str(index))
    progress = round(((index + 1) / total) * 100)
    return render_template(
        "quiz.html",
        quiz_title=session.get("quiz_title", "Quiz"),
        questions=questions,
        current_question=current_question,
        current_index=index,
        total=total,
        progress=progress,
        answers=answers,
        answered_count=answered_count,
        correct_count=correct_count,
        percent=percent,
        current_answer=current_answer,
        max_reachable=min(answered_count, total - 1),
    )


@app.route("/quiz/answer", methods=["POST"])
def answer():
    questions = session.get("questions")
    if not questions:
        return redirect(url_for("home"))

    index = int(request.form.get("index", 0))
    selected = request.form.get("selected")

    if selected is None:
        return redirect(url_for("quiz", index=index))

    answers = session.get("answers", {})
    q = questions[index]
    is_correct = selected == q["answer"]
    answers[str(index)] = {"selected": selected, "correct": is_correct}
    session["answers"] = answers

    next_index = index + 1
    if next_index >= len(questions):
        return redirect(url_for("result"))

    session["current"] = next_index
    return redirect(url_for("quiz", index=next_index))


@app.route("/result")
def result():
    questions = session.get("questions")
    answers = session.get("answers", {})
    if not questions:
        return redirect(url_for("home"))

    total = len(questions)
    correct = sum(1 for a in answers.values() if a.get("correct"))
    percent = round((correct / total) * 100, 1) if total else 0

    review = []
    for i, q in enumerate(questions):
        a = answers.get(str(i))
        review.append({
            "number": i + 1,
            "question": q["question"],
            "correct_answer": q["answer"],
            "selected": a["selected"] if a else None,
            "is_correct": bool(a and a["correct"]),
        })

    return render_template(
        "result.html",
        quiz_title=session.get("quiz_title", "Quiz"),
        total=total,
        correct=correct,
        wrong=total - correct,
        percent=percent,
        review=review,
    )


@app.route("/restart")
def restart():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)

