from datetime import datetime


def check_if_plus_one(school):
    danas = datetime.now()    
    # školska godina počinje u septembru tekuće godine
    if danas.month >= 9:
        # ako smo nakon septembra, tekuća školska godina je od septembra ove godine do septembra sledeće
        start_of_school_year = datetime(danas.year, 9, 1).date()
        end_of_school_year = datetime(danas.year + 1, 8, 31).date()
    else:
        # ako smo pre septembra, tekuća školska godina je od septembra prošle godine do septembra ove godine
        start_of_school_year = datetime(danas.year - 1, 9, 1).date()
        end_of_school_year = datetime(danas.year, 8, 31).date()

    # Proveravamo da li datum class_plus_one spada u tekuću školsku godinu
    if start_of_school_year <= school.class_plus_one <= end_of_school_year:
        plus_one_button = False
    else:
        plus_one_button = True
    return plus_one_button