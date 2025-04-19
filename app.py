from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from datetime import datetime
import os
from dotenv import load_dotenv
import ssl
import certifi

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDRQWMO2wHO3YW_LgCtAoukdWW6PLZCJvc")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# MongoDB Connection (Optional)
mongodb_available = False
try:
    from pymongo.mongo_client import MongoClient
    
    # Use the correct MongoDB connection string with your cluster ID
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://admin:dxs34Fu6WpQbgJsW@cluster0.l9fiajl.mongodb.net/hindi_summarizer?retryWrites=true&w=majority&appName=Cluster0")
    
    # Create a new client with explicit SSL configuration
    client = MongoClient(
        MONGO_URI,
        tlsCAFile=certifi.where(),
        ssl=True,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        connectTimeoutMS=30000,
        serverSelectionTimeoutMS=30000
    )
    
    # Test the connection with a ping
    client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
    
    db = client["hindi_summarizer"]
    summaries_collection = db["summaries"]
    mongodb_available = True
    
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    print("Application will continue without database functionality")
    mongodb_available = False

# Local storage fallback function
def save_summary_locally(summary_data):
    try:
        import json
        from pathlib import Path
        
        # Create data directory if it doesn't exist
        data_dir = Path("./data")
        data_dir.mkdir(exist_ok=True)
        
        # Generate a timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = data_dir / f"summary_{timestamp}.json"
        
        # Save the summary data as JSON
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, default=str)
            
        print(f"✅ Summary saved locally to {file_path}")
        return True
    except Exception as e:
        print(f"❌ Local save error: {e}")
        return False

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/db-status')
def db_status():
    if mongodb_available:
        try:
            # Test the connection is still working
            client.admin.command('ping')
            return "Database connected and working properly"
        except Exception as e:
            return f"Database connection error: {str(e)}"
    else:
        return "Database not configured - using local storage fallback"

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
            "compression_percentage": compression_value,
            "created_at": datetime.now()
        }
        
        # Try to save to MongoDB first
        if mongodb_available:
            try:
                # Insert the summary into MongoDB
                summaries_collection.insert_one(summary_data)
                print("✅ Summary saved to MongoDB")
            except Exception as e:
                print(f"❌ MongoDB save error: {e}")
                # Fall back to local storage
                save_summary_locally(summary_data)
        else:
            # MongoDB not available, use local storage
            save_summary_locally(summary_data)
        
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

if __name__ == "__main__":
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get("PORT", 5000))
    # Use 0.0.0.0 to bind to all addresses
    app.run(host="0.0.0.0", port=port)
