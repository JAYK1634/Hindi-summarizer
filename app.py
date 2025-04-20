from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDRQWMO2wHO3YW_LgCtAoukdWW6PLZCJvc")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
db_available = False

def init_db():
    if not DATABASE_URL:
        print("❌ No DATABASE_URL environment variable found")
        return False
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id SERIAL PRIMARY KEY,
            original_text TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            length VARCHAR(10) NOT NULL,
            original_sentences INTEGER,
            original_words INTEGER,
            summary_words INTEGER,
            compression_percentage REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ PostgreSQL database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

# Initialize the database
db_available = init_db()

def save_to_db(summary_data):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO summaries 
        (original_text, summary_text, length, original_sentences, original_words, summary_words, compression_percentage)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        cursor.close()
        conn.close()
        print("✅ Summary saved to PostgreSQL database")
        return True
    except Exception as e:
        print(f"❌ Database save error: {e}")
        return False

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/db-status')
def db_status():
    if not db_available:
        return "Database not configured correctly"
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM summaries")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return f"Database connected and working properly. Total summaries: {count}"
    except Exception as e:
        return f"Database error: {str(e)}"

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
        
        # Save to database
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
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get the most recent 10 summaries
        cursor.execute('''
        SELECT id, summary_text, length, original_words, summary_words, 
               compression_percentage, created_at
        FROM summaries
        ORDER BY created_at DESC
        LIMIT 10
        ''')
        
        summaries = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"summaries": summaries})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/view-summaries')
def view_summaries():
    try:
        # Connect to the database
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Query all summaries, ordered by newest first
        cur.execute("SELECT original_text, summary_text, created_at FROM summaries ORDER BY created_at DESC")
        rows = cur.fetchall()
        
        # Format the data for the template
        summaries = []
        for row in rows:
            summaries.append({
                'original_text': row[0],
                'summary_text': row[1],
                'timestamp': row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else 'Unknown'
            })
        
        # Close the database connection
        cur.close()
        conn.close()
        
        # Render the template with the summaries
        return render_template('summaries.html', summaries=summaries)
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/db-schema')
def db_schema():
    try:
        # Connect to the database
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Get table schema information
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'summaries'
        """)
        
        columns = cur.fetchall()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        # Return the schema information
        return jsonify({"table": "summaries", "columns": columns})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/admin/database')
def admin_database():
    try:
        # Basic HTML response without database queries
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Hindi Summarizer - Database Information</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                h1 { color: #2c3e50; text-align: center; }
                .container { max-width: 800px; margin: 0 auto; }
                .card { border: 1px solid #ddd; padding: 15px; margin: 15px 0; border-radius: 5px; }
                .btn { display: inline-block; padding: 10px 15px; background: #3498db; color: white; 
                       text-decoration: none; border-radius: 5px; margin: 10px 0; }
                .center { text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Hindi Summarizer Database Information</h1>
                
                <div class="card">
                    <h2>Database Structure</h2>
                    <p>Our application uses PostgreSQL to store summary data with the following structure:</p>
                    <ul>
                        <li><strong>id</strong>: Serial primary key</li>
                        <li><strong>original_text</strong>: The input Hindi text</li>
                        <li><strong>summary_text</strong>: The generated summary</li>
                        <li><strong>length</strong>: Selected summary length (short/long)</li>
                        <li><strong>original_sentences</strong>: Number of sentences in original text</li>
                        <li><strong>original_words</strong>: Number of words in original text</li>
                        <li><strong>summary_words</strong>: Number of words in summary</li>
                        <li><strong>compression_percentage</strong>: Percentage of text reduction</li>
                        <li><strong>created_at</strong>: Timestamp when summary was created</li>
                    </ul>
                </div>
                
                <div class="card">
                    <h2>Database Usage</h2>
                    <p>The database stores all summaries generated by users, allowing us to:</p>
                    <ul>
                        <li>Track usage patterns over time</li>
                        <li>Analyze compression ratios for different text lengths</li>
                        <li>Provide history functionality for users</li>
                        <li>Improve our summarization algorithm based on data</li>
                    </ul>
                </div>
                
                <div class="card">
                    <h2>Database Operations</h2>
                    <p>The application performs these database operations:</p>
                    <ul>
                        <li><strong>CREATE</strong>: When users generate new summaries</li>
                        <li><strong>READ</strong>: When viewing summary history</li>
                        <li><strong>QUERY</strong>: To generate statistics and analytics</li>
                    </ul>
                </div>
                
                <div class="center">
                    <a href="/view-summaries" class="btn">View All Summaries</a>
                    <a href="/" class="btn">Back to Summarizer</a>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

# This is needed for Gunicorn to find your app
application = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
