DROP TABLE IF EXISTS `app_post_office_type`;

CREATE TABLE `app_post_office_type` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `office_type` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
) ;
DROP TABLE IF EXISTS `app_post_offices`;

CREATE TABLE `app_post_offices` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `post_office_name` varchar(255) NOT NULL,
  `pin_code` varchar(20) NOT NULL,
  `post_office_type_id` int(11) NOT NULL,
  `postal_delivery_status_id` int(11) NOT NULL,
  `postal_division_id` int(11) NOT NULL,
  `postal_region_id` int(11) NOT NULL,
  `postal_circle_id` int(11) NOT NULL,
  `taluk_id` int(11) NOT NULL DEFAULT 1,
  `district_id` int(11) NOT NULL,
  `state_id` int(11) NOT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
  `latitude` varchar(50) DEFAULT NULL,
  `longitude` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ;


DROP TABLE IF EXISTS `app_postal_circle`;

CREATE TABLE `app_postal_circle` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `circle_name` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
) ;

DROP TABLE IF EXISTS `app_postal_delivery_status`;

CREATE TABLE `app_postal_delivery_status` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `delivery_status` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
) ;

DROP TABLE IF EXISTS `app_postal_division`;

CREATE TABLE `app_postal_division` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `circle_id` int(11) NOT NULL,
  `region_id` int(11) NOT NULL,
  `division_name` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
)  ;

DROP TABLE IF EXISTS `app_postal_region`;

CREATE TABLE `app_postal_region` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `circle_id` int(11) NOT NULL,
  `region_name` varchar(50) NOT NULL,
  PRIMARY KEY (`id`)
) ;

DROP TABLE IF EXISTS `app_postoffices`;

CREATE TABLE `app_postoffices` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `post_office_name` varchar(255) NOT NULL,
  `pin_code` varchar(20) NOT NULL,
  `taluk_id` int(11) NOT NULL,
  `district_id` int(11) NOT NULL,
  `state_id` int(11) NOT NULL,
  PRIMARY KEY (`id`)
)   ;
