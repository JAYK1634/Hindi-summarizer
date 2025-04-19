from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from datetime import datetime
import os
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDRQWMO2wHO3YW_LgCtAoukdWW6PLZCJvc")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# Set up SQLite database
DB_PATH = os.path.join(os.path.dirname(__file__), 'summaries.db')

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_text TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            length TEXT NOT NULL,
            original_sentences INTEGER,
            original_words INTEGER,
            summary_words INTEGER,
            compression_percentage REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()
        conn.close()
        print("✅ SQLite database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

# Initialize the database
db_available = init_db()

def save_to_db(summary_data):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO summaries 
        (original_text, summary_text, length, original_sentences, original_words, summary_words, compression_percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            summary_data["original_text"],
            summary_data["summary_text"],
            summary_data["length"],
            summary_data["original_sentences"],
            summary_data["original_words"],
            summary_data["summary_words"],
            summary_data["compression_percentage"]
        ))
        conn.commit()
        conn.close()
        print("✅ Summary saved to SQLite database")
        return True
    except Exception as e:
        print(f"❌ Database save error: {e}")
        return False

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/db-status')
def db_status():
    if db_available:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM summaries")
            count = cursor.fetchone()[0]
            conn.close()
            return f"Database connected and working properly. Total summaries: {count}"
        except Exception as e:
            return f"Database error: {str(e)}"
    else:
        return "Database not configured correctly"

@app.route('/summarize', methods=["POST"])
def summarize():
    input_text = request.form["text"]
    
    if input_text.strip() == "":
        return render_template("index.html", summary="⚠️ कृपया सारांश करने के लिए हिंदी टेक्स्ट दर्ज करें।")
    
    # Get user preferences for length
    length = request.form.get("length", "short")
    
    try:
        # Create appropriate instruction based on length
        if length == "short":
            prompt = f"""निम्नलिखित हिंदी टेक्स्ट का एक संक्षिप्त सारांश पैराग्राफ के रूप में बनाएं। कृपया 3-4 वाक्यों में मुख्य विचारों को कवर करें:

{input_text}"""
        else:  # long
            prompt = f"""निम्नलिखित हिंदी टेक्स्ट का एक विस्तृत सारांश पैराग्राफ के रूप में बनाएं। कृपया 8-10 वाक्यों में सभी महत्वपूर्ण विचारों और जानकारी को कवर करें:

{input_text}"""
        
        # Generate summary using Gemini
        response = model.generate_content(prompt)
        summary = response.text
        
        # Calculate compression ratio
        input_words = len(input_text.split())
        summary_words = len(summary.split())
        if input_words > 0:
            compression = f"{(1 - summary_words/input_words) * 100:.1f}%"
            compression_value = (1 - summary_words/input_words) * 100
        else:
            compression = "N/A"
            compression_value = 0
        
        # Count sentences and words in the input text
        sentences = len([s for s in input_text.split('।') if s.strip()])
        words = len(input_text.split())
        
        # Create summary data dictionary
        summary_data = {
            "original_text": input_text,
            "summary_text": summary,
            "length": length,
            "original_sentences": sentences,
            "original_words": words,
            "summary_words": summary_words,
            "compression_percentage": compression_value
        }
        
        # Save to SQLite database
        if db_available:
            save_to_db(summary_data)
        
    except Exception as e:
        summary = f"❌ त्रुटि: {str(e)}"
        compression = "N/A"
        sentences = 0
        words = 0
    
    return render_template("index.html", 
                          summary=summary, 
                          input_text=input_text,
                          length=length,
                          sentences=sentences,
                          words=words,
                          compression=compression)

@app.route('/history', methods=["GET"])
def history():
    if not db_available:
        return jsonify({"error": "Database not available"}), 500
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        # Get the most recent 10 summaries
        cursor.execute('''
        SELECT id, summary_text, length, original_words, summary_words, 
               compression_percentage, created_at
        FROM summaries
        ORDER BY created_at DESC
        LIMIT 10
        ''')
        
        rows = cursor.fetchall()
        summaries = []
        for row in rows:
            summaries.append({
                "id": row["id"],
                "summary": row["summary_text"],
                "length": row["length"],
                "original_words": row["original_words"],
                "summary_words": row["summary_words"],
                "compression": f"{row['compression_percentage']:.1f}%",
                "created_at": row["created_at"]
            })
        
        conn.close()
        return jsonify({"summaries": summaries})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get("PORT", 5000))
    # Use 0.0.0.0 to bind to all addresses
    app.run(host="0.0.0.0", port=port)
