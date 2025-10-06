# ai_agent/agent.py

import os
import json
from anthropic import Anthropic
from onetouch import db
from onetouch.models import Student, School
from onetouch.ai_agent.tools import TOOLS, process_tool_call

# Kreiraj Anthropic client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Ti si AI asistent za OneTouch aplikaciju - sistem za upravljanje 
đačkim uplatama. Pomažeš korisnicima da dobiju informacije o učenicima, dugovima i uplatama.

Kada koristiš alate:
- search_students: kada korisnik pominje ime učenika ali ne zna ID
- get_student_balance: za detaljno stanje pojedinačnog učenika (zahteva ID)
- get_section_overview: za finansijski pregled celog razreda ili odeljenja

Primeri korišćenja:
- "Prikaži Marka" → search_students + get_student_balance
- "Kako stoji 3/2?" → get_section_overview(class=3, section=2)
- "Koliko duguje četvrti razred?" → get_section_overview(class=4)

Važno:
- Ako search_students vrati više učenika, pitaj korisnika kog tačno misli
- Za get_section_overview, ako korisnik kaže samo razred (npr. "treći razred"), ne navodi odeljenje - prikaži podatke za ceo razred
- Kada prikazuješ iznose, koristi format: 12.345,67 din
- Za top dužnike, prikaži ih u čitljivom formatu

Odgovaraj na srpskom jeziku, jasno i precizno."""

def process_chat_message(message, user):
    """Procesira poruku korisnika i vraća odgovor od AI agenta"""
    
    # Inicijalna poruka
    conversation_history = [
        {"role": "user", "content": message}
    ]
    
    try:
        # Poziv Claude API sa tools
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history
        )
        
        # Tool calling loop
        while response.stop_reason == "tool_use":
            tool_results = []
            
            # Procesiranje svih tool poziva
            for content_block in response.content:
                if content_block.type == "tool_use":
                    tool_name = content_block.name
                    tool_input = content_block.input
                    tool_id = content_block.id
                    
                    print(f"🔧 AI agent koristi: {tool_name}")
                    print(f"   Parametri: {tool_input}")
                    
                    # Pozovi tool
                    result = process_tool_call(tool_name, tool_input, user)
                    
                    print(f"   ✅ Rezultat: {result}")
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(result)
                    })
            
            # Dodaj assistant poruku u istoriju
            conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            
            # Dodaj tool rezultate
            conversation_history.append({
                "role": "user",
                "content": tool_results
            })
            
            # Nastavi sa novim pozivom
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=conversation_history
            )
        
        # Izvuci finalni odgovor
        final_response = ""
        for content_block in response.content:
            if hasattr(content_block, "text"):
                final_response += content_block.text
        
        return {
            "success": True,
            "message": final_response
        }
        
    except Exception as e:
        print(f"❌ Greška u AI agentu: {str(e)}")
        return {
            "success": False,
            "message": f"Došlo je do greške: {str(e)}"
        }