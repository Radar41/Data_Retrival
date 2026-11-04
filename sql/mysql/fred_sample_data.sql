-- ============================================================================
--  FRED Metadata Catalog : sample data for testing the physical design (MySQL version;
--  identical to ../fred_sample_data.sql except `release` is quoted)
--  Real FRED identifiers and names; observation values are illustrative.
--  Production load comes from the FRED API via fred_load.py.
-- ============================================================================

-- lookups
INSERT INTO frequency VALUES ('D','Daily'),('W','Weekly'),('M','Monthly'),('Q','Quarterly'),('A','Annual');
INSERT INTO units VALUES ('%','Percent'),('Bil. of Chn. 2017 $','Billions of Chained 2017 Dollars'),
                         ('Index 1982-1984=100','Index 1982-1984=100'),('Thous. of Persons','Thousands of Persons');
INSERT INTO seasonal_adjustment VALUES ('SA','Seasonally Adjusted'),('NSA','Not Seasonally Adjusted'),
                                       ('SAAR','Seasonally Adjusted Annual Rate');

-- sources
INSERT INTO source VALUES (22,'U.S. Bureau of Labor Statistics','http://www.bls.gov/');
INSERT INTO source VALUES (18,'U.S. Bureau of Economic Analysis','http://www.bea.gov/');
INSERT INTO source VALUES (1,'Board of Governors of the Federal Reserve System (US)','http://www.federalreserve.gov/');

-- releases (release 53 is published jointly: demonstrates the M:N)
INSERT INTO `release` VALUES (50,'Employment Situation',TRUE,'http://www.bls.gov/ces/');
INSERT INTO `release` VALUES (10,'Consumer Price Index',TRUE,'http://www.bls.gov/cpi/');
INSERT INTO `release` VALUES (53,'Gross Domestic Product',TRUE,'http://www.bea.gov/national/');
INSERT INTO `release` VALUES (13,'G.17 Industrial Production and Capacity Utilization',TRUE,'http://www.federalreserve.gov/releases/g17/');
INSERT INTO `release` VALUES (999,'Discontinued Test Release',FALSE,NULL);   -- no series: exercises outer joins

INSERT INTO release_source VALUES (50,22),(10,22),(53,18),(53,1),(13,1),(999,1);

-- release dates (scheduled vs actual)
INSERT INTO release_date VALUES (50,DATE '2026-10-02','actual'),(50,DATE '2026-11-06','scheduled'),(50,DATE '2026-12-04','scheduled');
INSERT INTO release_date VALUES (10,DATE '2026-10-14','actual'),(10,DATE '2026-11-12','scheduled');
INSERT INTO release_date VALUES (53,DATE '2026-10-29','actual'),(53,DATE '2026-11-25','scheduled');
INSERT INTO release_date VALUES (13,DATE '2026-10-16','actual'),(13,DATE '2026-11-17','scheduled');

-- category hierarchy (real FRED ids): 0 root > 32991 Money,Banking.. / 10 Population,Employment.. > 32250 Unemployment Rate ...
INSERT INTO category VALUES (0,'Categories',NULL);
INSERT INTO category VALUES (10,'Population, Employment, & Labor Markets',0);
INSERT INTO category VALUES (12,'Current Population Survey (Household Survey)',10);
INSERT INTO category VALUES (32250,'Unemployment Rate',12);
INSERT INTO category VALUES (32455,'Prices',0);
INSERT INTO category VALUES (9,'Consumer Price Indexes (CPI and PCE)',32455);
INSERT INTO category VALUES (18,'National Accounts',0);
INSERT INTO category VALUES (106,'GDP/GNP',18);
INSERT INTO category VALUES (3,'Production & Business Activity',0);
INSERT INTO category VALUES (32262,'Industrial Production & Capacity Utilization',3);
INSERT INTO category VALUES (99999,'Empty Leaf (no series)',3);

-- tag groups and tags (real FRED group ids)
INSERT INTO tag_group VALUES ('freq','Frequency'),('gen','General or Concept'),('geo','Geography'),
                             ('seas','Seasonal Adjustment'),('src','Source'),('rls','Release');
INSERT INTO tag VALUES ('monthly','freq',NULL,90),('quarterly','freq',NULL,80),('usa','geo',NULL,100),
                       ('unemployment','gen',NULL,85),('cpi','gen',NULL,80),('gdp','gen',NULL,90),
                       ('sa','seas',NULL,95),('nsa','seas',NULL,80),('bls','src',NULL,90),('bea','src',NULL,85),
                       ('frb','src',NULL,80),('industrial production','gen',NULL,70),('rate','gen',NULL,75);

-- series
INSERT INTO series VALUES ('UNRATE','Unemployment Rate',50,'M','%','SA',DATE '1948-01-01',DATE '2026-09-01',TIMESTAMP '2026-10-02 07:46:00',94,'The unemployment rate represents the number of unemployed as a percentage of the labor force.');
INSERT INTO series VALUES ('UNRATENSA','Unemployment Rate (NSA)',50,'M','%','NSA',DATE '1948-01-01',DATE '2026-09-01',TIMESTAMP '2026-10-02 07:46:00',60,NULL);
INSERT INTO series VALUES ('PAYEMS','All Employees, Total Nonfarm',50,'M','Thous. of Persons','SA',DATE '1939-01-01',DATE '2026-09-01',TIMESTAMP '2026-10-02 07:46:00',92,'Total nonfarm payroll employment.');
INSERT INTO series VALUES ('CPIAUCSL','Consumer Price Index for All Urban Consumers: All Items in U.S. City Average',10,'M','Index 1982-1984=100','SA',DATE '1947-01-01',DATE '2026-09-01',TIMESTAMP '2026-10-14 07:38:00',93,NULL);
INSERT INTO series VALUES ('GDPC1','Real Gross Domestic Product',53,'Q','Bil. of Chn. 2017 $','SAAR',DATE '1947-01-01',DATE '2026-07-01',TIMESTAMP '2026-10-29 07:52:00',92,'BEA Account Code: A191RX');
INSERT INTO series VALUES ('INDPRO','Industrial Production: Total Index',13,'M','Index 1982-1984=100','SA',DATE '1919-01-01',DATE '2026-09-01',TIMESTAMP '2026-10-16 09:17:00',80,NULL);
INSERT INTO series VALUES ('STALE1','Stale Test Series (no updates since 2024)',13,'M','%','NSA',DATE '2000-01-01',DATE '2024-06-01',TIMESTAMP '2024-07-15 09:00:00',1,NULL);

INSERT INTO series_category VALUES ('UNRATE',32250),('UNRATENSA',32250),('PAYEMS',10),('CPIAUCSL',9),('GDPC1',106),('INDPRO',32262),('STALE1',32262);

INSERT INTO series_tag VALUES ('UNRATE','monthly'),('UNRATE','usa'),('UNRATE','unemployment'),('UNRATE','sa'),('UNRATE','bls'),('UNRATE','rate'),
 ('UNRATENSA','monthly'),('UNRATENSA','usa'),('UNRATENSA','unemployment'),('UNRATENSA','nsa'),('UNRATENSA','bls'),
 ('PAYEMS','monthly'),('PAYEMS','usa'),('PAYEMS','sa'),('PAYEMS','bls'),
 ('CPIAUCSL','monthly'),('CPIAUCSL','usa'),('CPIAUCSL','cpi'),('CPIAUCSL','sa'),('CPIAUCSL','bls'),
 ('GDPC1','quarterly'),('GDPC1','usa'),('GDPC1','gdp'),('GDPC1','sa'),('GDPC1','bea'),
 ('INDPRO','monthly'),('INDPRO','usa'),('INDPRO','industrial production'),('INDPRO','sa'),('INDPRO','frb');

-- observations with vintages. UNRATE 2026-07 was published once, revised once;
-- PAYEMS 2026-07 revised twice (payrolls get a 2nd and 3rd estimate); GDPC1 2026-04 revised twice.
INSERT INTO observation VALUES ('UNRATE',DATE '2026-06-01',DATE '2026-07-03',DATE '9999-12-31',4.1);
INSERT INTO observation VALUES ('UNRATE',DATE '2026-07-01',DATE '2026-08-07',DATE '2026-09-04',4.2);
INSERT INTO observation VALUES ('UNRATE',DATE '2026-07-01',DATE '2026-09-05',DATE '9999-12-31',4.3);
INSERT INTO observation VALUES ('UNRATE',DATE '2026-08-01',DATE '2026-09-05',DATE '9999-12-31',4.3);
INSERT INTO observation VALUES ('UNRATE',DATE '2026-09-01',DATE '2026-10-02',DATE '9999-12-31',4.4);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-07-01',DATE '2026-08-07',DATE '2026-09-04',159200);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-07-01',DATE '2026-09-05',DATE '2026-10-01',159150);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-07-01',DATE '2026-10-02',DATE '9999-12-31',159090);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-08-01',DATE '2026-09-05',DATE '2026-10-01',159230);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-08-01',DATE '2026-10-02',DATE '9999-12-31',159180);
INSERT INTO observation VALUES ('PAYEMS',DATE '2026-09-01',DATE '2026-10-02',DATE '9999-12-31',159250);
INSERT INTO observation VALUES ('CPIAUCSL',DATE '2026-08-01',DATE '2026-09-11',DATE '9999-12-31',323.4);
INSERT INTO observation VALUES ('CPIAUCSL',DATE '2026-09-01',DATE '2026-10-14',DATE '9999-12-31',324.1);
INSERT INTO observation VALUES ('GDPC1',DATE '2026-04-01',DATE '2026-07-30',DATE '2026-08-27',23510.2);
INSERT INTO observation VALUES ('GDPC1',DATE '2026-04-01',DATE '2026-08-28',DATE '2026-09-24',23540.8);
INSERT INTO observation VALUES ('GDPC1',DATE '2026-04-01',DATE '2026-09-25',DATE '9999-12-31',23552.1);
INSERT INTO observation VALUES ('GDPC1',DATE '2026-07-01',DATE '2026-10-29',DATE '9999-12-31',23690.0);
INSERT INTO observation VALUES ('INDPRO',DATE '2026-08-01',DATE '2026-09-17',DATE '2026-10-15',103.8);
INSERT INTO observation VALUES ('INDPRO',DATE '2026-08-01',DATE '2026-10-16',DATE '9999-12-31',103.9);
INSERT INTO observation VALUES ('INDPRO',DATE '2026-09-01',DATE '2026-10-16',DATE '9999-12-31',104.0);
INSERT INTO observation VALUES ('STALE1',DATE '2024-06-01',DATE '2024-07-15',DATE '9999-12-31',NULL);  -- FRED '.' becomes NULL
