\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '90s';
CREATE TEMP TABLE _approved_scope_118 (
    master_id integer PRIMARY KEY,
    canonical_id text NOT NULL,
    provider_id text NOT NULL,
    source_row_id integer NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    source_url text NOT NULL
) ON COMMIT DROP;
INSERT INTO _approved_scope_118 VALUES
(18,'AH-20261011105647-bf7687c9','02-24-017001-38001',18,25.47313200000002,49.641598999999985,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-24-017001-38001?type=TempRental'),
(19,'AH-20261011105647-468529f9','02-25-017001-2002',19,25.476485000000025,49.640687000000014,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-2002?type=TempRental'),
(20,'AH-20261011105647-1608887f','02-25-017001-2003',20,25.47609699999998,49.640536999999995,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-2003?type=TempRental'),
(21,'AH-20261011105647-437b2bd1','02-25-017001-3039',21,25.47354200000001,49.6345,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-3039?type=TempRental'),
(22,'AH-20261011105647-c1237d10','02-25-017001-6002',22,25.42735357800001,49.699016871000026,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-6002?type=TempRental'),
(23,'AH-20261011105647-a66123d1','02-25-017001-7001',23,25.426980463999996,49.698004860000026,'https://furas.momah.gov.sa/opportunity/02-25-017001-7001?type=TemporaryRental'),
(25,'AH-20261011105648-a9354516','02-25-017001-22001',25,25.72778526899998,50.16651234300002,'https://furas.momah.gov.sa/ar/opportunity/02-25-017001-22001?type=TemporaryRental'),
(26,'AH-20261011105648-17ddd4f7','02-25-017001-36002',26,25.32625308600001,49.559565994000025,'https://furas.momah.gov.sa/opportunity/02-25-017001-36002?type=TemporaryRental'),
(27,'AH-20261011105648-3afd08e5','02-25-017001-36001',27,25.32646562000002,49.56058560500003,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-36001?type=TempRental'),
(28,'AH-20261011105648-34d54a4d','02-25-017001-38003',28,25.313645483000016,49.58760848899999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-38003?type=TempRental'),
(29,'AH-20261011105648-42c459fb','02-25-017001-43001',29,25.47203760000002,49.63367099999999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-43001?type=TempRental'),
(31,'AH-20261011105648-ba65b9d7','02-25-017001-59007',31,25.313974024000004,49.58701706199997,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-59007?type=TempRental'),
(32,'AH-20261011105648-e4347879','02-25-017001-63005',32,25.288335867,49.52500099100001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-63005?type=TempRental'),
(33,'AH-20261011105648-0c99fd70','02-25-017001-63003',33,25.29340208000002,49.51843565899998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-63003?type=TempRental'),
(34,'AH-20261011105648-98ff8fbd','02-25-017001-63004',34,25.28836874199999,49.52226317200001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-63004?type=TempRental'),
(35,'AH-20261011105648-18962c50','02-25-017001-64001',35,25.28457268300002,49.520471455999996,'https://furas.momah.gov.sa/ar/opportunity/02-25-017001-64001?type=TemporaryRental'),
(36,'AH-20261011105648-eeceae08','02-25-017001-65001',36,25.28998571400001,49.51865560099998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-65001?type=TempRental'),
(37,'AH-20261011105648-566a1fb3','02-25-017001-65002',37,25.287773663999985,49.515915724000024,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-65002?type=TempRental'),
(38,'AH-20261011105648-5a48f52b','02-25-017001-66001',38,25.287857900999995,49.516615109999975,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66001?type=TempRental'),
(39,'AH-20261011105648-86447d58','02-25-017001-66002',39,25.291435795999973,49.50914605700001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66002?type=TempRental'),
(40,'AH-20261011105648-e421080e','02-25-017001-66006',40,25.28829962399999,49.51723738300001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66006?type=TempRental'),
(41,'AH-20261011105648-8a07ee35','02-25-017001-66009',41,25.288141988000007,49.52200836200001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66009?type=TempRental'),
(42,'AH-20261011105648-30723bd5','02-25-017001-66003',42,25.287726675999977,49.51581581200003,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66003?type=TempRental'),
(43,'AH-20261011105648-1a46879a','02-25-017001-66008',43,25.288170483999977,49.51815737999999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66008?type=TempRental'),
(44,'AH-20261011105649-80390eb9','02-25-017001-66010',44,25.287997689999997,49.52202512600002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66010?type=TempRental'),
(45,'AH-20261011105649-d18067c5','02-25-017001-66011',45,25.28782004499999,49.51583793999998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66011?type=TempRental'),
(46,'AH-20261011105649-804a06a4','02-25-017001-66012',46,25.288417245000005,49.520722912999986,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66012?type=TempRental'),
(47,'AH-20261011105649-6c872366','02-25-017001-67001',47,25.469287090000023,49.63498697,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-67001?type=TempRental'),
(48,'AH-20261011105649-852e0722','02-25-017001-69002',48,25.28833297,49.523873837999986,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-69002?type=TempRental'),
(49,'AH-20261011105649-931a0563','02-25-017001-68001',49,25.291657938000014,49.509004172000004,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-68001?type=TempRental'),
(50,'AH-20261011105649-79a0c485','02-25-017001-69003',50,25.28701367000002,49.51493135300001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-69003?type=TempRental'),
(51,'AH-20261011105649-0201e7d4','02-25-017001-71001',51,25.288425237000013,49.518604735,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-71001?type=TempRental'),
(52,'AH-20261011105649-a3cd0d57','02-25-017001-71004',52,25.287496509999983,49.51546414699999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-71004?type=TempRental'),
(53,'AH-20261011105649-91ed7297','02-25-017001-71005',53,25.287324418000026,49.51538016400002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-71005?type=TempRental'),
(54,'AH-20261011105649-a0672eb0','02-25-017001-72001',54,25.37535901000001,49.77150077499999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-72001?type=TempRental'),
(55,'AH-20261011105649-21dd6e04','02-25-017001-73001',55,25.605776361999972,49.54634844999998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-73001?type=TempRental'),
(56,'AH-20261011105649-015cc26d','02-25-017001-75001',56,25.292503426999986,49.518517539000015,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-75001?type=TempRental'),
(57,'AH-20261011105649-b46afeaa','02-25-017001-77001',57,25.289670445000013,49.51136669800002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77001?type=TempRental'),
(58,'AH-20261011105649-c8db73d5','02-25-017001-77003',58,25.28760420399999,49.51265952199998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77003?type=TempRental'),
(59,'AH-20261011105649-5d2e06ce','02-25-017001-77004',59,25.293182004000016,49.51886615400002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77004?type=TempRental'),
(60,'AH-20261011105649-6bfabde1','02-25-017001-77002',60,25.294903794999982,49.51851344300002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77002?type=TempRental'),
(61,'AH-20261011105649-4f6e5914','02-25-017001-77005',61,25.293298408,49.518758865999985,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77005?type=TempRental'),
(62,'AH-20261011105649-a4f70020','02-25-017001-77006',62,25.287482945000022,49.515481206000004,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-77006?type=TempRental'),
(63,'AH-20261011105649-740951d7','02-25-017001-81001',63,25.46302374999999,49.63777779999998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-81001?type=TempRental'),
(65,'AH-20261011105649-b22d6225','02-25-017001-84002',65,25.457840753000028,49.55188096699999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-84002?type=TempRental'),
(66,'AH-20261011105650-c4b8e4b4','02-25-017001-85001',66,25.35105477100001,49.568161996000015,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-85001?type=TempRental'),
(67,'AH-20261011105650-85ed184e','02-25-017001-86001',67,25.475152750999996,49.639996897,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-86001?type=TempRental'),
(68,'AH-20261011105650-7dda38f4','02-25-017001-89001',68,25.475709618999986,49.64028263199998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-89001?type=TempRental'),
(69,'AH-20261011105650-d7b2323e','02-26-017001-1',69,25.35370599700002,49.545213468999975,'https://furas.momah.gov.sa/opportunity/02-26-017001-1?type=TemporaryRental'),
(71,'AH-20261011105650-be2799ce','02-26-017001-9001',71,25.326691084000004,49.56157446999998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-9001?type=TempRental'),
(72,'AH-20261011105650-2b582726','02-26-017001-12003',72,25.41629794900001,49.71656311100003,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-12003?type=TempRental'),
(73,'AH-20261011105650-9a2462fd','02-26-017001-22001',73,25.39577700000001,49.59773200000001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-22001?type=TempRental'),
(76,'AH-20261011105650-967b53d2','02-26-017001-24002',76,25.471961796000016,49.63429130999998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-24002?type=TempRental'),
(77,'AH-20261011105650-36479495','02-26-017001-24003',77,25.475951383999984,49.64032608299999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-24003?type=TempRental'),
(79,'AH-20261011105650-9afd0ac2','02-26-017001-32004',79,25.368115165000006,49.544544961999975,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-32004?type=TempRental'),
(80,'AH-20261011105650-1c3623b5','02-26-017001-32006',80,25.36918386000002,49.54518034900002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-32006?type=TempRental'),
(81,'AH-20261011105650-8fff7ffc','02-26-017001-34001',81,25.472619683999994,49.63467815600001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-34001?type=TempRental'),
(82,'AH-20261011105650-b9b88a65','02-26-017001-36001',82,25.271895298000004,49.577284573999975,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-36001?type=TempRental'),
(83,'AH-20261011105650-84e8868f','02-26-017001-37001',83,25.326128214999983,49.564759630000026,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-37001?type=TempRental'),
(84,'AH-20261011105650-2add8f66','02-26-017001-37002',84,25.356508362,49.632802975999994,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-37002?type=TempRental'),
(85,'AH-20261011105651-3a7efe62','02-26-017001-43001',85,25.437713003,49.665813721999996,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-43001?type=TempRental'),
(86,'AH-20261011105651-9c94d601','02-26-017001-44001',86,25.32658920900002,49.560890325,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-44001?type=TempRental'),
(87,'AH-20261011105651-4c302413','02-26-017001-44004',87,25.358248946999993,49.558909700000015,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-44004?type=TempRental'),
(88,'AH-20261011105651-0c6d6ab6','02-26-017001-44005',88,25.326761642999998,49.56150796700001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-44005?type=TempRental'),
(89,'AH-20261011105651-9a910223','02-26-017001-44006',89,25.36918158499998,49.545081632000006,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-44006?type=TempRental'),
(90,'AH-20261011105651-5eb0e783','26-09-2422346',90,25.45100084799998,49.51929818899998,'https://furas.momah.gov.sa/ar/opportunity/26-09-2422346?type=Investment'),
(91,'AH-20261011105651-a3059cd0','26-09-2422553',91,25.451790754,49.529361318999975,'https://furas.momah.gov.sa/ar/opportunity/26-09-2422553?type=Investment'),
(92,'AH-20261011105651-7007d3ac','02-26-017001-47002',92,25.40186399999999,49.59917899999999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-47002?type=TempRental'),
(93,'AH-20261011105651-3b3c9c3c','02-26-017001-48003',93,25.36907863800002,49.545042437000006,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-48003?type=TempRental'),
(94,'AH-20261011105651-f33dd377','02-26-017001-49002',94,25.346512614000005,49.603849087000015,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-49002?type=TempRental'),
(95,'AH-20261011105651-c904292c','02-26-017001-49003',95,25.346274309000023,49.60452872799999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-49003?type=TempRental'),
(96,'AH-20261011105651-e25a3f15','06-26-183737-49004',96,25.30644909900002,49.56751436600001,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-183737-49004?type=Investment'),
(97,'AH-20261011105651-e71f3d3d','26-09-2439514',97,25.42039351400001,49.742578993999985,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439514?type=Investment'),
(98,'AH-20261011105651-b7ff6708','06-26-183737-49005',98,25.456537631000003,49.55242943500002,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-183737-49005?type=Investment'),
(99,'AH-20261011105651-a88fa646','06-26-183737-49007',99,25.408759513000007,49.55879522599997,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-183737-49007?type=Investment'),
(100,'AH-20261011105651-2925405a','26-09-2439570',100,25.45705276299998,49.55299926999999,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439570?type=Investment'),
(101,'AH-20261011105651-371a0a93','06-26-183737-49009',101,25.420581992999985,49.74240537100002,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-183737-49009?type=Investment'),
(102,'AH-20261011105651-100798cf','06-26-183737-46013',102,25.35841789699998,49.560769042000004,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-183737-46013?type=Investment'),
(103,'AH-20261011105652-f9950aca','26-09-2439658',103,25.409109693000005,49.55898007100001,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439658?type=Investment'),
(104,'AH-20261011105652-0f77fc8d','26-09-2439662',104,25.38819175200001,49.59563294399999,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439662?type=Investment'),
(105,'AH-20261011105652-98765a0e','26-09-2439674',105,25.42046473900001,49.74270713200002,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439674?type=Investment'),
(106,'AH-20261011105652-f587a727','06-26-187795-34003',106,25.360761000000025,49.59860629999997,'https://furas.momah.gov.sa/index.php/ar/opportunity/06-26-187795-34003?type=Investment'),
(107,'AH-20261011105652-aa9e604a','01-26-017001-39029',107,25.329259999999977,49.604750000000024,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-39029?type=Investment'),
(111,'AH-20261011105652-b56f1496','02-25-017001-63002',111,25.287311968999973,49.51534441299998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-63002?type=TempRental'),
(112,'AH-20261011105652-a3d10d8e','02-25-017001-65003',112,25.286516502999973,49.51372771199999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-65003?type=TempRental'),
(113,'AH-20261011105652-4b053a7f','02-25-017001-66004',113,25.288522134000004,49.518977466000024,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66004?type=TempRental'),
(114,'AH-20261011105652-6805dbc1','02-25-017001-66005',114,25.29078115599998,49.510315272000014,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66005?type=TempRental'),
(115,'AH-20261011105652-d1589f10','02-25-017001-66007',115,25.291052164000007,49.51862207300002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-66007?type=TempRental'),
(116,'AH-20261011105652-2f6eb0eb','02-25-017001-69001',116,25.292524807000007,49.51879909899998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-69001?type=TempRental'),
(117,'AH-20261011105652-b9bff309','02-25-017001-68002',117,25.28814259400002,49.52275267499999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-68002?type=TempRental'),
(118,'AH-20261011105652-502ffb95','02-25-017001-71003',118,25.28963778399998,49.51857598700002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-71003?type=TempRental'),
(119,'AH-20261011105652-e18d80c4','02-25-017001-70001',119,25.28757787699999,49.51604168799997,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-70001?type=TempRental'),
(120,'AH-20261011105652-adfad0b6','02-25-017001-71002',120,25.28641759499999,49.51430593600003,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-71002?type=TempRental'),
(121,'AH-20261011105653-af16d2ed','02-25-017001-73002',121,25.60609728899999,49.54630841699998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-73002?type=TempRental'),
(122,'AH-20261011105653-883f690d','02-25-017001-77007',122,25.287429589999988,49.51531490899998,'https://furas.momah.gov.sa/opportunity/02-25-017001-77007?type=TemporaryRental'),
(123,'AH-20261011105653-36636760','02-25-017001-83002',123,25.47205147400001,49.63396243,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-83002?type=TempRental'),
(124,'AH-20261011105653-ab763d05','02-25-017001-86002',124,25.475091005000024,49.63971392399998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-86002?type=TempRental'),
(125,'AH-20261011105653-1f01a34a','02-25-017001-86003',125,25.475269584999978,49.64007065800001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-25-017001-86003?type=TempRental'),
(126,'AH-20261011105653-2c4a25f9','02-26-017001-5001',126,25.368841703999976,49.59278197200001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-5001?type=TempRental'),
(127,'AH-20261011105653-6cde5118','02-26-017001-8001',127,25.364811257999975,49.72691119799998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-8001?type=TempRental'),
(128,'AH-20261011105653-be326c08','02-26-017001-9002',128,25.32650197999999,49.560517679999975,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-9002?type=TempRental'),
(129,'AH-20261011105653-88baca25','02-26-017001-23001',129,25.390006000000028,49.563315999999986,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-23001?type=TempRental'),
(130,'AH-20261011105653-9129a3b3','02-26-017001-24005',130,25.473088897000025,49.63804512500002,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-24005?type=TempRental'),
(131,'AH-20261011105653-0afb24b1','02-26-017001-32002',131,25.369198141000027,49.54521632299998,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-32002?type=TempRental'),
(132,'AH-20261011105653-fd14fb36','02-26-017001-32005',132,25.36865153299999,49.54484222299999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-32005?type=TempRental'),
(133,'AH-20261011105653-24e75322','02-26-017001-32007',133,25.346380329,49.60421775200001,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-32007?type=TempRental'),
(134,'AH-20261011105653-01522bf5','02-26-017001-39001',134,25.352079075000006,49.568124098,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-39001?type=TempRental'),
(136,'AH-20261011105653-ea5feb3c','02-26-017001-44003',136,25.357427746999974,49.558879287000025,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-44003?type=TempRental'),
(137,'AH-20261011105653-8ef3197f','02-26-017001-45001',137,25.42697489599999,49.69688937199999,'https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-45001?type=TempRental'),
(138,'AH-20261011105653-8d041477','26-09-2422468',138,25.452317244000028,49.51963421200003,'https://furas.momah.gov.sa/ar/opportunity/26-09-2422468?type=Investment'),
(139,'AH-20261011105654-75a464ce','26-09-2422527',139,25.448425953000026,49.51590761800003,'https://furas.momah.gov.sa/ar/opportunity/26-09-2422527?type=Investment'),
(141,'AH-20261011105654-5f155ac5','26-09-2439653',141,25.457076563999976,49.55338605100002,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439653?type=Investment'),
(142,'AH-20261011105654-c209a449','26-09-2439686',142,25.30680929099998,49.567564842000024,'https://furas.momah.gov.sa/index.php/ar/opportunity/26-09-2439686?type=Investment'),
(163,'AH-20261011111414-abc577e8','01-26-017001-23001',2834,25.390822000000014,49.66241400000001,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-23001?type=Investment'),
(164,'AH-20261011111415-7845ad39','01-26-017001-39001',140,25.526516000000015,49.60361,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-39001?type=Investment'),
(192,'AH-20261011111428-559ef48d','01-26-017001-36001',135,25.548997999999983,49.68509499999999,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-36001?type=Investment'),
(193,'AH-20261011111429-1df50137','01-26-017001-27002',75,25.634749,49.544749000000024,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-27002?type=Investment'),
(195,'AH-20261011111430-798b7aa6','01-26-017001-27001',74,25.63518399999998,49.54383200000001,'https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-27001?type=Investment');
CREATE TEMP TABLE _other_excluded_372 (master_id integer PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _other_excluded_372 VALUES (10),(11),(12),(13),(14),(15),(16),(17),(24),(70),(108),(109),(110),(205),(206),(207),(226),(227),(230),(231),(232),(234),(235),(237),(239),(240),(241),(242),(246),(248),(249),(251),(253),(255),(257),(258),(260),(262),(308),(309),(310),(311),(312),(313),(314),(315),(316),(317),(318),(319),(320),(321),(322),(323),(324),(325),(339),(340),(341),(342),(343),(344),(345),(346),(347),(348),(349),(350),(351),(352),(353),(354),(355),(356),(357),(358),(359),(360),(361),(362),(363),(364),(365),(366),(367),(368),(369),(370),(371),(372),(373),(374),(375),(376),(377),(378),(379),(380),(381),(382),(383),(384),(385),(386),(387),(388),(389),(390),(391),(392),(393),(394),(395),(396),(397),(398),(399),(400),(401),(402),(403),(404),(405),(406),(407),(408),(409),(410),(411),(412),(413),(414),(415),(416),(417),(418),(419),(420),(421),(422),(423),(424),(425),(426),(427),(428),(429),(430),(431),(432),(433),(434),(435),(436),(437),(438),(439),(440),(441),(442),(443),(444),(445),(446),(447),(448),(449),(450),(451),(452),(453),(454),(455),(456),(457),(458),(459),(460),(461),(462),(463),(464),(465),(466),(467),(468),(469),(470),(471),(472),(473),(474),(475),(476),(477),(478),(479),(480),(481),(482),(483),(484),(485),(486),(487),(488),(489),(490),(491),(492),(493),(494),(495),(496),(497),(498),(499),(500),(501),(502),(503),(504),(505),(506),(507),(508),(509),(510),(511),(512),(513),(514),(515),(516),(517),(518),(519),(520),(521),(522),(523),(524),(525),(526),(527),(528),(529),(530),(531),(532),(533),(534),(535),(536),(537),(538),(539),(540),(541),(542),(543),(544),(545),(546),(547),(548),(549),(550),(551),(552),(553),(554),(555),(556),(557),(558),(559),(560),(561),(562),(563),(564),(565),(566),(567),(568),(569),(570),(571),(572),(573),(574),(575),(576),(577),(587),(588),(590),(592),(594),(595),(597),(598),(600),(602),(604),(606),(608),(609),(610),(612),(614),(615),(616),(617),(1041),(1618),(2005),(2693),(2972),(2988),(3066),(4205),(4208),(4601),(5045),(5047),(5049),(5050),(5052),(5053),(5055),(5056),(5057),(5059),(5060),(5061),(5062),(5065),(5067),(5069),(5070),(5072),(5074),(5075),(5089),(5090),(5357),(5510),(6060),(6061),(6062),(6068),(6069),(6071),(6073),(6074),(6075),(6077),(6079),(6081),(6083),(6084),(6086),(6092),(6093),(6094),(6096),(6097),(6330),(6382),(6540);
DO $guard$
DECLARE
    v_count integer;
    v_locked integer;
    v_source_locked integer;
    v_other_count integer;
    v_bad integer;
BEGIN
    SELECT count(*) INTO v_count FROM _approved_scope_118;
    IF v_count <> 118 THEN RAISE EXCEPTION 'APPROVAL_SET_COUNT expected=118 actual=%',v_count; END IF;
    IF EXISTS (SELECT 1 FROM _approved_scope_118 WHERE master_id=64) THEN RAISE EXCEPTION 'HELD_MASTER_64_IN_TARGET_SET'; END IF;
    SELECT count(*) INTO v_count FROM (SELECT master_id FROM _approved_scope_118 GROUP BY master_id HAVING count(*)>1) d;
    IF v_count <> 0 THEN RAISE EXCEPTION 'DUPLICATE_APPROVED_MASTER_IDS'; END IF;
    PERFORM o.id FROM opportunities o JOIN _approved_scope_118 a ON a.master_id=o.id ORDER BY o.id FOR UPDATE OF o;
    GET DIAGNOSTICS v_locked = ROW_COUNT;
    IF v_locked <> 118 THEN RAISE EXCEPTION 'MASTER_LOCK_COUNT expected=118 actual=%',v_locked; END IF;
    PERFORM so.id FROM source_opportunities so JOIN _approved_scope_118 a ON a.source_row_id=so.id ORDER BY so.id FOR UPDATE OF so;
    GET DIAGNOSTICS v_source_locked = ROW_COUNT;
    IF v_source_locked <> 118 THEN RAISE EXCEPTION 'SOURCE_LOCK_COUNT expected=118 actual=%',v_source_locked; END IF;
    SELECT count(*) INTO v_other_count FROM _other_excluded_372 i JOIN opportunities o ON o.id=i.master_id;
    IF v_other_count <> 372 THEN RAISE EXCEPTION 'OTHER_EXCLUDED_SET_COUNT expected=372 actual=%',v_other_count; END IF;
    SELECT count(*) INTO v_bad
    FROM _approved_scope_118 a
    LEFT JOIN opportunities o ON o.id=a.master_id
    LEFT JOIN geographic_reference_units g ON g.id=o.geography_reference_unit_id
    LEFT JOIN geographic_reference_units pg ON pg.id=g.parent_id
    WHERE o.id IS NULL
       OR o.canonical_id IS DISTINCT FROM a.canonical_id
       OR o.geographic_scope IS DISTINCT FROM 'UNSPECIFIED'
       OR o.latitude IS DISTINCT FROM a.latitude
       OR o.longitude IS DISTINCT FROM a.longitude
       OR o.merged_into_id IS NOT NULL
       OR o.manual_review_required IS TRUE
       OR g.level IS DISTINCT FROM 'governorate'
       OR g.external_id IS DISTINCT FROM '501'
       OR pg.external_id IS DISTINCT FROM '5'
       OR (SELECT count(*) FROM source_opportunities sx JOIN sources ss ON ss.id=sx.source_id WHERE sx.master_opportunity_id=o.id AND ss.source_key='furas') <> 1
       OR NOT EXISTS (
            SELECT 1 FROM source_opportunities so JOIN sources s ON s.id=so.source_id
            WHERE so.id=a.source_row_id AND s.source_key='furas'
              AND so.source_opportunity_id=a.provider_id
              AND so.master_opportunity_id=o.id
              AND so.source_url=a.source_url
              AND (so.raw_data_json->'geometry'->>'y')::double precision=a.latitude
              AND (so.raw_data_json->'geometry'->>'x')::double precision=a.longitude
       )
       OR o.coordinate_provenance_json->>'verification_method' IS DISTINCT FROM 'DIRECT_SOURCE_COORDINATE'
       OR o.coordinate_provenance_json->>'source_record_identity_matches' IS DISTINCT FROM 'true'
       OR (o.coordinate_provenance_json->>'source_record_id')::integer IS DISTINCT FROM a.source_row_id
       OR o.coordinate_provenance_json->>'source_opportunity_id' IS DISTINCT FROM a.provider_id
       OR (o.coordinate_provenance_json->>'source_latitude')::double precision IS DISTINCT FROM a.latitude
       OR (o.coordinate_provenance_json->>'source_longitude')::double precision IS DISTINCT FROM a.longitude
       OR o.coordinate_provenance_json#>>'{boundary_validation,status}' IS DISTINCT FROM 'VERIFIED_IN_SAUDI'
       OR EXISTS (SELECT 1 FROM opportunity_data_conflicts c WHERE c.opportunity_id=o.id AND c.status IN ('OPEN','PENDING'))
       OR EXISTS (SELECT 1 FROM location_reviews lr WHERE lr.source_record_id=a.source_row_id AND lr.status IN ('OPEN','PENDING'));
    IF v_bad <> 0 THEN RAISE EXCEPTION 'LIVE_APPROVAL_REVALIDATION_FAILURE rows=%',v_bad; END IF;
END
$guard$;
CREATE TEMP TABLE _approved_before ON COMMIT DROP AS
SELECT o.id AS master_id,to_jsonb(o) AS row_json
FROM opportunities o JOIN _approved_scope_118 a ON a.master_id=o.id;
CREATE TEMP TABLE _held64_before ON COMMIT DROP AS
SELECT o.id AS master_id,to_jsonb(o) AS row_json FROM opportunities o WHERE o.id=64;
CREATE TEMP TABLE _other372_before ON COMMIT DROP AS
SELECT o.id AS master_id,to_jsonb(o) AS row_json
FROM opportunities o JOIN _other_excluded_372 i ON i.master_id=o.id;
CREATE TEMP TABLE _source_before ON COMMIT DROP AS
SELECT so.id AS source_row_id,to_jsonb(so) AS row_json,
       (SELECT count(*) FROM source_observations ob WHERE ob.source_opportunity_id=so.id) AS observations_count
FROM source_opportunities so JOIN _approved_scope_118 a ON a.source_row_id=so.id;
CREATE TEMP TABLE _update_result (updated_count integer NOT NULL) ON COMMIT DROP;
WITH changed AS (
    UPDATE opportunities o
       SET geographic_scope='SPECIFIC_LOCATION'
      FROM _approved_scope_118 a
     WHERE o.id=a.master_id AND o.geographic_scope='UNSPECIFIED'
    RETURNING o.id
)
INSERT INTO _update_result SELECT count(*)::integer FROM changed;
DO $postcheck$
DECLARE
    v_updated integer;
    v_changed integer;
BEGIN
    SELECT updated_count INTO v_updated FROM _update_result;
    IF v_updated <> 118 THEN RAISE EXCEPTION 'UPDATE_COUNT expected=118 actual=%',v_updated; END IF;
    SELECT count(*) INTO v_changed FROM _approved_scope_118 a JOIN opportunities o ON o.id=a.master_id
     WHERE o.geographic_scope IS DISTINCT FROM 'SPECIFIC_LOCATION';
    IF v_changed <> 0 THEN RAISE EXCEPTION 'POST_SCOPE_CHECK_FAILURE rows=%',v_changed; END IF;
    SELECT count(*) INTO v_changed FROM _approved_before b JOIN opportunities o ON o.id=b.master_id
     WHERE (to_jsonb(o)-'geographic_scope') IS DISTINCT FROM (b.row_json-'geographic_scope');
    IF v_changed <> 0 THEN RAISE EXCEPTION 'UNAUTHORIZED_MASTER_FIELD_CHANGE rows=%',v_changed; END IF;
    SELECT count(*) INTO v_changed FROM _held64_before b JOIN opportunities o ON o.id=b.master_id
     WHERE to_jsonb(o) IS DISTINCT FROM b.row_json;
    IF v_changed <> 0 OR (SELECT count(*) FROM _held64_before) <> 1 THEN RAISE EXCEPTION 'HELD_MASTER_64_CHANGED'; END IF;
    SELECT count(*) INTO v_changed FROM _other372_before b JOIN opportunities o ON o.id=b.master_id
     WHERE to_jsonb(o) IS DISTINCT FROM b.row_json;
    IF v_changed <> 0 OR (SELECT count(*) FROM _other372_before) <> 372 THEN RAISE EXCEPTION 'OTHER_372_EXCLUDED_CHANGED rows=%',v_changed; END IF;
    SELECT count(*) INTO v_changed FROM _source_before b JOIN source_opportunities so ON so.id=b.source_row_id
     WHERE to_jsonb(so) IS DISTINCT FROM b.row_json
        OR (SELECT count(*) FROM source_observations ob WHERE ob.source_opportunity_id=so.id) IS DISTINCT FROM b.observations_count;
    IF v_changed <> 0 OR (SELECT count(*) FROM _source_before) <> 118 THEN RAISE EXCEPTION 'SOURCE_IDENTITY_OR_OBSERVATION_CHANGED rows=%',v_changed; END IF;
END
$postcheck$;
SELECT 'TXID',txid_current()::text,'isolation',current_setting('transaction_isolation');
SELECT master_id FROM _approved_scope_118 ORDER BY master_id;
COMMIT;
