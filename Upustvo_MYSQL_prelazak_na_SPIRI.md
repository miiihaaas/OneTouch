# Uputstvo za promene u MySQL bazi pri prelasku na SPIRI nadogradnju

Ovo uputstvo daje instrukcije koje promene treba uraditi u MySQL bazi na serveru prilikom prelaska na SPIRI nadogradnju aplikacije. U nastavku su opisane izmene koje je potrebno napraviti u tabelama **school**, **service_item**, i **student_payment**.

## 1. Izmene u `school` tabeli

Potrebno je dodati novu kolonu `school_bank_accounts` koja će čuvati informacije u JSON formatu  i `class_plus_one` koji će da čuva datum kada su svi učenici prebačeni u sledeći razred. 

SQL naredba za ovu izmenu:

```sql
ALTER TABLE `school`
ADD COLUMN `school_bank_accounts` JSON
ADD COLUMN `class_plus_one` DATE;
```

## 2. Izmene u `service_item` tabeli

U tabeli `service_item` potrebno je dodati sledeće dve nove kolone:
* `bank_account ` sa tipom VARCHAR(255),
* `reference_number_spiri` sa tipom VARCHAR(255),

SQL naredba za ovu izmenu:
```sql
ALTER TABLE `service_item`
ADD COLUMN `bank_account` VARCHAR(255),
ADD COLUMN `reference_number_spiri` VARCHAR(255);
```

## 3. Izmene u `student_payment` tabeli

U tabeli `student_payment` potrebno je dodati novu kolonu `bank_account` sa tipom VARCHAR(255).


SQL naredba za ovu izmenu:
```sql
ALTER TABLE `student_payment`
ADD COLUMN `bank_account` VARCHAR(255);
```

#

### Nakon primene ovih izmena, baza će biti spremna za nadogradnju aplikacije na SPIRI verziju.