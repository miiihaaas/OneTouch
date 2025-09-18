# Uputstvo za promene u MySQL bazi pri prelasku na SPIRI nadogradnju

Ovo uputstvo daje instrukcije koje promene treba uraditi u MySQL bazi na serveru prilikom prelaska na SPIRI nadogradnju aplikacije. U nastavku su opisane izmene koje je potrebno napraviti u tabelama **school**, **service_item**, i **student_payment**.

## 1. Izmene u `school` tabeli

Potrebno je dodati nove kolone:
* `school_bank_accounts` koja čuva informacije u JSON formatu
* `class_plus_one` koja čuva datum kada su svi učenici prebačeni u sledeći razred
* `license_expiry_date` koja čuva datum isteka licence za školu
* `last_license_email_date` koja čuva datum slanja mejla o isteku licence
* `school_phone_number` koja čuva kontakt telefon škole

SQL naredba za ovu izmenu:

```sql
ALTER TABLE `school`
ADD COLUMN IF NOT EXISTS `school_bank_accounts` JSON,
ADD COLUMN IF NOT EXISTS `class_plus_one` DATE,
ADD COLUMN IF NOT EXISTS `license_expiry_date` DATE,
ADD COLUMN IF NOT EXISTS `last_license_email_date` DATE,
ADD COLUMN IF NOT EXISTS `school_phone_number` VARCHAR(255);
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
DELIMITER //

CREATE PROCEDURE add_columns_if_not_exists()
BEGIN
   SET @dbname = DATABASE();
   
   -- school table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'school_bank_accounts') THEN
       ALTER TABLE `school` ADD COLUMN `school_bank_accounts` JSON;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'class_plus_one') THEN
       ALTER TABLE `school` ADD COLUMN `class_plus_one` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'license_expiry_date') THEN
       ALTER TABLE `school` ADD COLUMN `license_expiry_date` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'last_license_email_date') THEN
       ALTER TABLE `school` ADD COLUMN `last_license_email_date` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'school_phone_number') THEN
       ALTER TABLE `school` ADD COLUMN `school_phone_number` VARCHAR(255);
   END IF;
   
   -- service_item table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'service_item' AND COLUMN_NAME = 'bank_account') THEN
       ALTER TABLE `service_item` ADD COLUMN `bank_account` VARCHAR(255);
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'service_item' AND COLUMN_NAME = 'reference_number_spiri') THEN
       ALTER TABLE `service_item` ADD COLUMN `reference_number_spiri` VARCHAR(255);
   END IF;

   -- student_payment table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'student_payment' AND COLUMN_NAME = 'bank_account') THEN
       ALTER TABLE `student_payment` ADD COLUMN `bank_account` VARCHAR(255);
   END IF;
END //

DELIMITER ;

CALL add_columns_if_not_exists();
DROP PROCEDURE IF EXISTS add_columns_if_not_exists;
```

# Oprez: ako želiš da se na sve db primene promene u tabelama, sa velikim oprezom pokušati ovaj kod
```sql
DELIMITER //

-- Prva procedura za dodavanje kolona
CREATE PROCEDURE add_columns_if_not_exists()
BEGIN
   SET @dbname = DATABASE();
   
   -- school table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'school_bank_accounts') THEN
       ALTER TABLE `school` ADD COLUMN `school_bank_accounts` JSON;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'class_plus_one') THEN
       ALTER TABLE `school` ADD COLUMN `class_plus_one` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'license_expiry_date') THEN
       ALTER TABLE `school` ADD COLUMN `license_expiry_date` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'last_license_email_date') THEN
       ALTER TABLE `school` ADD COLUMN `last_license_email_date` DATE;
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'school' AND COLUMN_NAME = 'school_phone_number') THEN
       ALTER TABLE `school` ADD COLUMN `school_phone_number` VARCHAR(255);
   END IF;
   
   -- service_item table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'service_item' AND COLUMN_NAME = 'bank_account') THEN
       ALTER TABLE `service_item` ADD COLUMN `bank_account` VARCHAR(255);
   END IF;
   
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'service_item' AND COLUMN_NAME = 'reference_number_spiri') THEN
       ALTER TABLE `service_item` ADD COLUMN `reference_number_spiri` VARCHAR(255);
   END IF;

   -- student_payment table
   IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'student_payment' AND COLUMN_NAME = 'bank_account') THEN
       ALTER TABLE `student_payment` ADD COLUMN `bank_account` VARCHAR(255);
   END IF;
END //

-- Druga procedura za prolazak kroz sve baze
CREATE PROCEDURE add_columns_to_all_databases()
BEGIN
   DECLARE done INT DEFAULT FALSE;
   DECLARE db_name VARCHAR(255);
   DECLARE db_cursor CURSOR FOR 
       SELECT SCHEMA_NAME 
       FROM INFORMATION_SCHEMA.SCHEMATA 
       WHERE SCHEMA_NAME NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys');
   DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

   OPEN db_cursor;
   read_loop: LOOP
       FETCH db_cursor INTO db_name;
       IF done THEN
           LEAVE read_loop;
       END IF;

       SET @sql = CONCAT('USE `', db_name, '`; 
           CALL add_columns_if_not_exists();');
       PREPARE stmt FROM @sql;
       EXECUTE stmt;
       DEALLOCATE PREPARE stmt;
   END LOOP;
   CLOSE db_cursor;
END //

DELIMITER ;

-- Izvršavanje
CALL add_columns_to_all_databases();

-- Čišćenje
DROP PROCEDURE IF EXISTS add_columns_if_not_exists;
DROP PROCEDURE IF EXISTS add_columns_to_all_databases;
```

#


### Nakon primene ovih izmena, bazaće biti spremna za nadogradnju aplikacije na SPIRI verziju.
# Pelazak na SPIRI

### Promene u .env fajlu
dodati sledeće redove u .env fajlu:
```bash
LICENSE_NOTIFICATION_DAYS='30,15,3'
LICENSE_NOTIFICATION_EMAILS='office@studioimplicit.rs,miiihaaas@gmail.com'
```
zatim izmeniti promenjive u .env fajlu:
* `EMAIL_USER` u `MAIL_USERNAME`
* `EMAIL_PASS` u `MAIL_PASSWORD`

```bash
MAIL_USERNAME
MAIL_PASSWORD
```
#

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