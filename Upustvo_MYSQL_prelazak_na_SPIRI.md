# Uputstvo za promene u MySQL bazi pri prelasku na SPIRI nadogradnju

Ovo uputstvo daje instrukcije koje promene treba uraditi u MySQL bazi na serveru prilikom prelaska na SPIRI nadogradnju aplikacije. U nastavku su opisane izmene koje je potrebno napraviti u tabelama **school**, **service_item**, i **student_payment**.

## 1. Izmene u `school` tabeli

Potrebno je dodati nove kolone:
* `school_bank_accounts` koja čuva informacije u JSON formatu
* `class_plus_one` koja čuva datum kada su svi učenici prebačeni u sledeći razred
* `license_expiry_date` koja čuva datum isteka licence za školu
* `last_license_email_date` koja čuva datum slanja mejla o isteku licence

SQL naredba za ovu izmenu:

```sql
ALTER TABLE `school`
ADD COLUMN IF NOT EXISTS `school_bank_accounts` JSON,
ADD COLUMN IF NOT EXISTS `class_plus_one` DATE,
ADD COLUMN IF NOT EXISTS `license_expiry_date` DATE,
ADD COLUMN IF NOT EXISTS `last_license_email_date` DATE;
```

## 2. Izmene u `service_item` tabeli

U tabeli `service_item` potrebno je dodati sledeće dve nove kolone:
* `bank_account ` sa tipom VARCHAR(255),
* `reference_number_spiri` sa tipom VARCHAR(255),

SQL naredba za ovu izmenu:
```sql
ALTER TABLE `service_item`
ADD COLUMN IF NOT EXISTS `bank_account` VARCHAR(255),
ADD COLUMN IF NOT EXISTS `reference_number_spiri` VARCHAR(255);
```

## 3. Izmene u `student_payment` tabeli

U tabeli `student_payment` potrebno je dodati novu kolonu `bank_account` sa tipom VARCHAR(255).


SQL naredba za ovu izmenu:
```sql
ALTER TABLE `student_payment`
ADD COLUMN IF NOT EXISTS `bank_account` VARCHAR(255);
```
Ukupni SQL kod za sve tri stavke:
```sql
ALTER TABLE `school`
ADD COLUMN IF NOT EXISTS `school_bank_accounts` JSON,
ADD COLUMN IF NOT EXISTS `class_plus_one` DATE,
ADD COLUMN IF NOT EXISTS `license_expiry_date` DATE,
ADD COLUMN IF NOT EXISTS `last_license_email_date` DATE;
ALTER TABLE `service_item`
ADD COLUMN IF NOT EXISTS `bank_account` VARCHAR(255),
ADD COLUMN IF NOT EXISTS `reference_number_spiri` VARCHAR(255);
ALTER TABLE `student_payment`
ADD COLUMN IF NOT EXISTS `bank_account` VARCHAR(255);
```
#

### Nakon primene ovih izmena, bazaće biti spremna za nadogradnju aplikacije na SPIRI verziju.
# Pelazak na SPIRI
U terminalu na serveru imamo sledeće komande:
## 1. Git pull
```bash
git pull
```
## 2. Git checkout
```bash
git checkout spiri
```

# Sledeći koraci
Nakon prilagođavanja strukture baze podataka potrebno je izmeniti sledeće podatke u bazi:
## 1. `school_bank_accounts` kolona u tabeli `school`

U koloni `school_bank_accounts` treba da se nalazi JSON podatak u formatu:
```json
{"bank_accounts": [{"bank_account_number": "840-0000000000000-33", "reference_number_spiri": "0000000000000000000"}]}
```
* prilagoditi podatke školi.
* preko aplikacije dodati ostale bankovne račune. Link prilagoditi tako da se umesto xxxx u URL-u nalazi ID škole.
```url
https://uplatnice.online/xxxx/school
```

## 2. `bank_account` i `reference_number_spiri` kolone u tabeli `service_item`
Nakon što se u aplikaciju unesu svi bankovni računi (tačka 1.), potrebno je izmeniti podatke u tabeli `service_item` u sledečim kolonama:
* U aplikaciji treba da se izmeni vrednost u polju **Broj bankovnog računa** za svaki detalj usluge. Link prilagoditi tako da se umesto xxxx u URL-u nalazi ID usluge.
```url
https://uplatnice.online/xxxx/service_profile_list
```
* Izabrati jednu od ponuđenih opcija u polju **Broj bankovnog računa**.
* Kolone (**Račun** i **Poziv na broj**) treba da imaju definisane vrednosti (da nisu None).

# Postoji mogućnost da će trebati dodatni koraci da se rade. Te korake dodati u ovaj dokument.