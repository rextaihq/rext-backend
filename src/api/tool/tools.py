import re

def count_text_metrics(text: str):
    # Count characters including spaces
    char_count = len(text)

    # Count words: split the text by whitespace and count resulting elements
    words = re.split(r'\s+', text.strip())
    word_count = len([word for word in words if word])
    
    # Count sentences: a rough estimate by counting common end punctuation
    sentence_count = text.count('.') + text.count('!') + text.count('?')

    # Count paragraphs: split by double newline characters using a loop
    paragraph_list = text.strip().split('\n\n')
    paragraph_count = 0
    for p in paragraph_list:
        if p.strip(): # Check if the paragraph content is not empty
            paragraph_count += 1

    # Estimate reading time (e.g., 200 words per minute average)
    min_read = round(word_count / 200) if word_count > 0 else 0

    return {
        'words': word_count,
        'characters': char_count,
        'sentences': sentence_count,
        'paragraphs': paragraph_count,
        'min_read': min_read
    }
