import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def generate_image(prompt: str, model: str = "dall-e-3", size: str = "1024x1024"):
    """
    Generates an image using OpenAI's DALL-E model and returns the URL.
    
    Args:
        prompt (str): The text description of the image.
        model (str): The model to use (default "dall-e-3").
        size (str): Image resolution (1024x1024, 1024x1792, or 1792x1024).

    Returns:
        str: The URL of the generated image.
    """
    # Create the OpenAI client
    # Assumes OPENAI_API_KEY is set in your environment variables
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality="standard",  # or "hd"
        )
        
        # Extract the URL from the response
        image_url = response.data[0].url
        return image_url

    except Exception as e:
        print(f"Error generating image: {e}")
        return None

# # Example Usage:
# url = generate_image("A futuristic city at sunset in cyberpunk style")
# print(url)
