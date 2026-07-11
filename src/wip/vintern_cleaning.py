import json
import re

def clean_json_string(s):
    # Remove control characters except for tab, newline, and carriage return
    # Also keep form feed.
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    # The file has unescaped newlines inside strings. A simple replacement is risky,
    # but for this specific file, it might be the only way.
    # Let's try to replace newlines inside quotes.
    # This is tricky. A simpler approach is to just load with strict=False
    return s

def clean_vintern_results(input_json_path, output_json_path):
    """
    Reads data from a JSON file, decodes Unicode escape sequences,
    and saves it to another JSON file, handling malformed Unicode and control characters.

    Args:
        input_json_path (str): The path to the input JSON file.
        output_json_path (str): The path to the output JSON file.
    """
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        # The json.loads with strict=False should handle control characters.
        # The main issue seems to be the surrogate characters on output.
        data = json.loads(raw_text, strict=False)

        # To handle the surrogate issue on writing, we must encode to a string
        # and then decode back, but this time handling surrogates properly before
        # letting json.dump handle it.
        # Let's dump it to a string first with indentation for readability.
        temp_json_string = json.dumps(data, ensure_ascii=False, indent=2)

        # Now write this string to a file, handling any lingering encoding issues.
        with open(output_json_path, 'w', encoding='utf-8', errors='surrogatepass') as f:
            f.write(temp_json_string)

        print(f"Successfully cleaned {input_json_path} and saved to {output_json_path}")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    input_file_path = 'vintern_results.json'
    output_file_path = 'vintern_results_cleaned.json'
    
    clean_vintern_results(input_file_path, output_file_path)
