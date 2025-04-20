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

@app.route('/admin/database', methods=['GET'])
def admin_database():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get table information
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [table['table_name'] for table in cursor.fetchall()]
        
        # Get column information for summaries table
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'summaries'
        """)
        columns = cursor.fetchall()
        
        # Get sample data
        cursor.execute("SELECT * FROM summaries ORDER BY created_at DESC LIMIT 5")
        sample_data = cursor.fetchall()
        
        # Get count of records
        cursor.execute("SELECT COUNT(*) FROM summaries")
        count = cursor.fetchone()['count']
        
        # Get some statistics
        cursor.execute("""
            SELECT 
                MIN(created_at) as oldest_entry,
                MAX(created_at) as newest_entry,
                AVG(compression_percentage)::numeric(10,2) as avg_compression,
                MIN(original_words) as min_words,
                MAX(original_words) as max_words
            FROM summaries
        """)
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # Create HTML response
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Hindi Summarizer - Database Information</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; color: #333; }}
                h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
                h2 {{ color: #3498db; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .stats {{ display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }}
                .stat-box {{ background-color: #f8f9fa; border-radius: 5px; padding: 15px; flex: 1; min-width: 200px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #3498db; margin: 10px 0; }}
                .stat-label {{ font-size: 14px; color: #7f8c8d; }}
                pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .back-link {{ margin-top: 30px; display: block; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Hindi Summarizer Database Information</h1>
                
                <div class="stats">
                    <div class="stat-box">
                        <div class="stat-label">Total Summaries</div>
                        <div class="stat-value">{count}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Average Compression</div>
                        <div class="stat-value">{stats['avg_compression']}%</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Largest Text</div>
                        <div class="stat-value">{stats['max_words']} words</div>
                    </div>
                </div>
                
                <h2>Database Tables</h2>
                <ul>
                    {"".join(f"<li>{table}</li>" for table in tables)}
                </ul>
                
                <h2>Summaries Table Structure</h2>
                <table>
                    <tr>
                        <th>Column Name</th>
                        <th>Data Type</th>
                    </tr>
                    {"".join(f"<tr><td>{col['column_name']}</td><td>{col['data_type']}</td></tr>" for col in columns)}
                </table>
                
                <h2>Database Statistics</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>First Entry Date</td>
                        <td>{stats['oldest_entry'].strftime('%Y-%m-%d %H:%M:%S') if stats['oldest_entry'] else 'N/A'}</td>
                    </tr>
                    <tr>
                        <td>Latest Entry Date</td>
                        <td>{stats['newest_entry'].strftime('%Y-%m-%d %H:%M:%S') if stats['newest_entry'] else 'N/A'}</td>
                    </tr>
                    <tr>
                        <td>Average Compression</td>
                        <td>{stats['avg_compression']}%</td>
                    </tr>
                    <tr>
                        <td>Smallest Text</td>
                        <td>{stats['min_words']} words</td>
                    </tr>
                    <tr>
                        <td>Largest Text</td>
                        <td>{stats['max_words']} words</td>
                    </tr>
                </table>
                
                <h2>Recent Entries (5 most recent)</h2>
                <table>
                    <tr>
                        <th>ID</th>
                        <th>Length</th>
                        <th>Original Words</th>
                        <th>Summary Words</th>
                        <th>Compression</th>
                        <th>Created At</th>
                    </tr>
                    {"".join(f"""
                    <tr>
                        <td>{entry['id']}</td>
                        <td>{entry['length']}</td>
                        <td>{entry['original_words']}</td>
                        <td>{entry['summary_words']}</td>
                        <td>{entry['compression_percentage']:.1f}%</td>
                        <td>{entry['created_at'].strftime('%Y-%m-%d %H:%M:%S') if entry['created_at'] else 'N/A'}</td>
                    </tr>
                    """ for entry in sample_data)}
                </table>
                
                <h2>Sample Text and Summaries</h2>
                {"".join(f"""
                <div style="margin-bottom: 30px; border: 1px solid #eee; padding: 15px; border-radius: 5px;">
                    <h3>Summary #{entry['id']}</h3>
                    <h4>Original Text:</h4>
                    <pre>{entry['original_text'][:300]}{'...' if len(entry['original_text']) > 300 else ''}</pre>
                    <h4>Summary:</h4>
                    <pre>{entry['summary_text']}</pre>
                </div>
                """ for entry in sample_data)}
                
                <a href="/" class="back-link">Back to Summarizer</a>
            </div>
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        return f"Error accessing database: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
