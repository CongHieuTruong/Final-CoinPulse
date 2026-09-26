# File: app.py
from flask import Flask, request, render_template_string

app = Flask(__name__)

# Extremely basic HTML interface with an input field
HTML_TEMPLATE = '''
    <h1>CryptoScope MVP - Echo Test</h1>
    <form method="POST">
        <label>Enter a keyword (e.g., Bitcoin):</label><br>
        <input type="text" name="user_input" required>
        <button type="submit">Submit!</button>
    </form>
    {% if result %}
        <h2 style="color: green;">System response: You just entered "{{ result }}"</h2>
    {% endif %}
'''

@app.route('/', methods=['GET', 'POST'])
def home():
    user_input = None
    if request.method == 'POST':
        user_input = request.form.get('user_input') # Receive data
    return render_template_string(HTML_TEMPLATE, result=user_input) # Echo to the screen

if __name__ == '__main__':
    app.run(debug=True)