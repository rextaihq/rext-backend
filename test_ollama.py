import textstat

# The content you want to analyze
test_data = """
Playing games is fun. It helps you relax and enjoy your time with friends. 
However, some games are very complex and require a high level of strategic thinking.
"""

# 1. READABILITY (0 to 100, higher is easier)
reading_ease = textstat.flesch_reading_ease(test_data)
print(f"Flesch Reading Ease: {reading_ease}")

# 2. GRADE LEVEL (The school grade required to understand the text)
kincaid_grade = textstat.flesch_kincaid_grade(test_data)
print(f"Flesch-Kincaid Grade Level: {kincaid_grade}")

# 3. COMPLEXITY / TECHNICAL LEVEL
# Gunning Fog is great for checking if text is too "business-heavy" or wordy
fog_index = textstat.gunning_fog(test_data)
# SMOG is the gold standard for medical or healthcare complexity
smog = textstat.smog_index(test_data)

print(f"Gunning Fog Index: {fog_index}")
print(f"SMOG Index: {smog}")

# 4. OTHER POPULAR METRICS
print(f"Automated Readability Index: {textstat.automated_readability_index(test_data)}")
print(f"Coleman-Liau Index: {textstat.coleman_liau_index(test_data)}")
print(f"Dale-Chall Score: {textstat.dale_chall_readability_score(test_data)}")

# 5. THE CONSENSUS (Best for a general "Final Score")
# This combines all the above tests into one simple grade recommendation
consensus = textstat.text_standard(test_data)
print(f"Overall Consensus: {consensus}")

# 6. BASE STATISTICS (Raw counts)
print(f"Syllable Count: {textstat.syllable_count(test_data)}")
print(f"Word Count: {textstat.lexicon_count(test_data)}")
print(f"Sentence Count: {textstat.sentence_count(test_data)}")