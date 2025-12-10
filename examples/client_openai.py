"""
Exemple: Client OpenAI pointant vers le proxy local.

Usage:
    pip install openai
    python examples/client_openai.py
"""
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================

client = OpenAI(
    base_url="http://localhost:8007/v1",  # TON PROXY
    api_key="not-needed"  # L'API key est gérée côté serveur
)


# ============================================================
# EXEMPLE 1: Chat simple (non-streaming)
# ============================================================

def chat_simple():
    print("=" * 50)
    print("EXEMPLE 1: Chat simple")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant concis."},
            {"role": "user", "content": "Donne-moi 3 conseils pour bien dormir."}
        ],
        stream=False
    )
    
    print(f"Réponse: {response.choices[0].message.content}")
    print(f"Model: {response.model}")
    print(f"ID: {response.id}")
    print()


# ============================================================
# EXEMPLE 2: Chat streaming
# ============================================================

def chat_streaming():
    print("=" * 50)
    print("EXEMPLE 2: Chat streaming")
    print("=" * 50)
    
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Raconte-moi une blague courte."}
        ],
        stream=True
    )
    
    print("Réponse: ", end="", flush=True)
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)
    print("\n")


# ============================================================
# EXEMPLE 3: Conversation multi-tours
# ============================================================

def chat_conversation():
    print("=" * 50)
    print("EXEMPLE 3: Conversation multi-tours")
    print("=" * 50)
    
    messages = [
        {"role": "system", "content": "Tu es un prof de maths patient."}
    ]
    
    questions = [
        "C'est quoi une dérivée ?",
        "Donne-moi un exemple simple.",
        "Et pour x² ?"
    ]
    
    for q in questions:
        print(f"User: {q}")
        messages.append({"role": "user", "content": q})
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=False
        )
        
        answer = response.choices[0].message.content
        messages.append({"role": "assistant", "content": answer})
        print(f"Assistant: {answer}\n")


# ============================================================
# EXEMPLE 4: JSON Format (response_format)
# ============================================================

def chat_json_format():
    print("=" * 50)
    print("EXEMPLE 4: JSON Format")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system", 
                "content": "Tu es un assistant qui répond UNIQUEMENT en JSON valide."
            },
            {
                "role": "user", 
                "content": "Donne-moi 3 films de science-fiction avec leur année et note sur 10."
            }
        ],
        response_format={"type": "json_object"},
        stream=False
    )
    
    import json
    content = response.choices[0].message.content
    print(f"Réponse brute: {content}")
    
    # Parser le JSON
    data = json.loads(content)
    print(f"Réponse parsée: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()


# ============================================================
# EXEMPLE 5: JSON Schema (structured outputs)
# ============================================================

def chat_json_schema():
    print("=" * 50)
    print("EXEMPLE 5: JSON Schema (Structured Outputs)")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Génère un utilisateur fictif."}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "user",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "nom": {"type": "string"},
                        "age": {"type": "integer"},
                        "email": {"type": "string"},
                        "hobbies": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["nom", "age", "email", "hobbies"],
                    "additionalProperties": False
                }
            }
        },
        stream=False
    )
    
    import json
    content = response.choices[0].message.content
    data = json.loads(content)
    
    print(f"Utilisateur généré:")
    print(f"  Nom: {data['nom']}")
    print(f"  Age: {data['age']}")
    print(f"  Email: {data['email']}")
    print(f"  Hobbies: {', '.join(data['hobbies'])}")
    print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n🚀 Client OpenAI → Proxy local (http://localhost:8007/v1)\n")

    # JSON format
    chat_json_format()
    
    # JSON schema (structured outputs)
    chat_json_schema()
    
    print("✅ Terminé!")
