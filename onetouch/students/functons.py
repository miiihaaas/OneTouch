from datetime import datetime, timedelta


# Funkcija koja određuje za koju školsku godinu se računa promena
def get_school_year_for_change(change_date):
    """
    Avgust - promena se računa za NAREDNU školsku godinu
    Septembar - promena se računa za TEKUĆU školsku godinu
    """
    if change_date.month == 8:
        # Avgust - za narednu školsku godinu (koja počinje u septembru)
        return (change_date.year, change_date.year + 1)
    elif change_date.month == 9:
        # Septembar - za tekuću školsku godinu
        return (change_date.year, change_date.year + 1)
    else:
        return None

def check_if_plus_one(school):
    """
    Proverava da li treba prikazati dugme za +1
    Dugme se prikazuje ako:
    1. Smo u periodu 15. avgust - 30. septembar
    2. Nije već urađena promena za trenutnu školsku godinu
    """
    danas = datetime.now()
    
    # Prvo proveravamo da li smo u dozvoljenom periodu
    if not ((danas.month == 8 and danas.day >= 15) or danas.month == 9):
        return False
    
    # Ako nikad nije rađena promena, prikaži dugme
    if not school.class_plus_one:
        return True

    # Proveravamo da li bi trenutna promena bila za istu školsku godinu kao poslednja
    current_change_school_year = get_school_year_for_change(danas)
    last_change_school_year = get_school_year_for_change(school.class_plus_one)
    return current_change_school_year != last_change_school_year