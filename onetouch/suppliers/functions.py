from transliterate import translit


def convert_to_latin(text):
    if any('А' <= char <= 'я' for char in text):  # Provera da li string sadrži ćirilične karaktere
        return translit(text, 'sr', reversed=True)  # Konvertovanje u latinicu
    return text  # Ako je već latinica, vraća isti tekst
