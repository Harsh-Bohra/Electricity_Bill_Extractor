# Electricity Bill Data Extraction Project

Hey there! 👋 This is my project for automatically pulling out key info from Indian electricity bill PDFs. It was a bit of a rollercoaster, but I got it working using some cool tech like OCR and a large language model.

## What it Does

Basically, you upload your electricity bill PDFs, and this app tries its best to read them and give you back the important details (like your name, bill amount, dates, etc.) in a nice, organized table (CSV) and individual structured files (JSON).

## How it Works (My Approach)

I broke it down into a few steps:

1.  **PDF to Picture:** First, I convert the PDF pages into images. Computers are better at "seeing" text in pictures than directly in PDFs for OCR. I just focused on the first page since that usually has most of the info.
2.  **Cleaning the Picture:** I do some basic stuff to the image – make it black and white, try to get rid of weird dots (noise), and make the text a bit sharper. This helps the next step read the text better.
3.  **Reading the Text (OCR):** I use Tesseract OCR to scan the picture and pull out all the text it can find. This gives me a big blob of raw text.
4.  **Finding the Right Info (LLM Magic):** This was the tricky part! I feed the raw text into a large language model (Google Gemini, after trying *a lot* of others). I tell it exactly what pieces of info I need (like "Customer Name", "Amount Payable", etc.) and ask it to give it back to me neatly formatted as JSON.
5.  **Checking and Fixing:** The data from the LLM isn't always perfect. I added some checks to make sure numbers look like numbers, dates are in a consistent format, and try to fix a few common mistakes the LLM might make.
6.  **Organizing Results:** If you upload multiple bills, I gather all the extracted info and put it into one big table (CSV) and also keep the individual JSON files.

I built a simple web interface using Streamlit so it's easy to upload files and download the results.

## Why I Chose What I Chose

* **`pdf2image` + Poppler:** Standard tools for turning PDFs into images. They just work.
* **`pytesseract` + Tesseract OCR:** A solid, widely used OCR engine. `pytesseract` makes it easy to use in Python.
* **Google Gemini (gemini-1.5-flash-001):** Okay, this was the survivor after a long battle!
    * I really wanted to use open-source models like Llama, TinyLlama, Mistral, Deepseek, or even OpenAI stuff.
    * My laptop just couldn't handle them locally – not enough graphics memory (CUDA).
    * Moving to Google Colab helped with GPUs, but the free tier has limits on what GPUs you get and how much memory they have, plus usage caps. It was still tough to run the bigger models reliably.
    * I even tried running inference directly on Hugging Face, but my API tokens vanished super fast!
    * **The BIGGEST reason I couldn't use fancy LayoutLLMs or similar models:** Indian electricity bills are WILDLY unstructured. They don't follow a standard template at all. Text is all over the place, tables are weird, and things aren't neatly aligned. Models like LayoutLM that rely heavily on *visual layout* just got completely confused. Gemini, being more text-focused and powerful, was much better at just reading the text blob and finding the patterns based on keywords, even if the layout was messy.
    * Gemini was powerful enough for the text extraction, great at giving me JSON output, and accessible within my project constraints.

## The Struggles (Challenges Faced)

Man, this project had some tough spots:

* **NO DATASET:** This was the absolute worst! You cannot find a public dataset of Indian electricity bills anywhere online (obviously, it's sensitive personal data). I had to do some serious "Juggad" (resourceful workaround) to find a few sample bills, mostly from places like Scribd. This meant I had very limited data to test with, and couldn't train anything specific.
* **Model/Platform Headaches:** Like I said, finding a model that was powerful enough *and* that I could actually run without hitting hardware or free-tier limits was a massive trial-and-error process.
* **Can't Really Evaluate Properly:** Because I had no labeled dataset (no "correct" answers for each field), I couldn't calculate standard accuracy.
* **Finals!** My university exams hit right in the middle of this, cutting into my development time and making it impossible to manually label enough bills to do a proper accuracy check.

So, my evaluation is based on how *complete* the data extraction is, not how *accurate* each specific field is compared to a ground truth.

## How I Evaluated (My Metric)

Since I couldn't check if the *values* were correct, I checked if the *fields* were filled.

I used "Extraction Coverage":

$$\text{Extraction Coverage (%) } = \left( \frac{\text{Number of Fields I Successfully Extracted (Not Blank)}}{\text{Total Number of Fields I Expected to Extract}} \right) \times 100$$

This just tells me what percentage of the requested fields the app managed to find *something* for.

## How to Run It Yourself

Here's how to get this running on your computer:

1.  **Get Python:** Make sure you have Python 3.7 or newer installed. Grab it from [python.org](https://www.python.org/downloads/).
2.  **Install Tesseract OCR:** This reads the text from images.
    * **Windows:** Download from [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki). Run the installer. You might need to add its install folder (where `tesseract.exe` is) to your system's PATH, or you'll have to tell the Python code where to find it (see step 6).
    * **macOS (using Homebrew):** Open Terminal: `brew install tesseract`
    * **Linux (Debian/Ubuntu):** Open Terminal: `sudo apt update && sudo apt install tesseract-ocr`
3.  **Install Poppler:** This helps convert PDFs to images.
    * **Windows:** Download binaries from [http://blog.alivate.com.au/poppler-windows/](http://blog.alivate.com.au/poppler-windows/). Extract the zip. You might need to add the `bin` folder from the extracted files to your system's PATH, or tell the Python code where to find it (see step 6).
    * **macOS (using Homebrew):** Open Terminal: `brew install poppler`
    * **Linux (Debian/Ubuntu):** Open Terminal: `sudo apt update && sudo apt install poppler-utils`
4.  **Get the Code:** Save the Python code for the Streamlit app (the `bill_processor_app.py` file) to a folder on your computer.
5.  **Create `requirements.txt`:** In the *same folder* as your Python file, create a file named `requirements.txt` and put this inside:
    ```
    streamlit
    google-generativeai
    pdf2image
    Pillow
    pytesseract
    pandas
    numpy
    ```
6.  **Set up Python Environment:**
    * Open your terminal or command prompt.
    * Go to your project folder using `cd your/project/folder`.
    * Create a virtual environment (good practice!): `python -m venv .venv`
    * Activate the environment:
        * macOS/Linux: `source .venv/bin/activate`
        * Windows CMD: `.venv\Scripts\activate`
        * Windows PowerShell: `.venv\Scripts\Activate.ps1`
    * Install the libraries: `pip install -r requirements.txt`
7.  **Configure Tesseract/Poppler Paths (If Needed):** If you skipped adding Tesseract/Poppler to your system's PATH, you'll need to edit the `bill_processor_app.py` file. Find the commented-out lines near the top like `# pytesseract.pytesseract.tesseract_cmd = r''` and the `convert_from_path` call. Uncomment them and put the full path to your `tesseract.exe` (or `tesseract`) and the Poppler `bin` directory.
8.  **Run the App:** With your virtual environment active in the terminal, run:
    ```bash
    streamlit run bill_processor_app.py
    ```
9.  **Open in Browser:** Your browser should automatically open to `http://localhost:8501` where the app is running!

## Ideas for Making it Better (Productionization)

If I were taking this further, I'd want to add:

* **Better Error Messages:** More specific info if something goes wrong.
* **Handling Weird Bills:** Improve how it deals with scanned copies or really messy layouts. Maybe try different OCR settings or models.
* **Handling More Pages:** Right now, it only looks at the first page.
* **Let Users Fix Mistakes:** A way for the user to see the extracted data and correct any errors the AI made.
* **Make it Faster/Handle More Bills:** Right now it does one bill at a time. For lots of bills, it would need to process them all at once (parallel processing).
* **Security:** **Definitely** remove the hardcoded API key and use environment variables or Streamlit's secrets feature.
* **Proper Testing:** Write automated tests to make sure different parts work correctly.
* **Easier Setup:** Maybe package it in a way that Tesseract/Poppler installation is smoother, or use cloud services that handle these dependencies.

Let me know if you encounter any questions while running it, I would happily explain.
