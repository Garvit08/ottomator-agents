/*
SQLyog Community v13.3.0 (64 bit)
MySQL - 8.0.27 : Database - idataops_realtime_insights
*********************************************************************
*/

/*!40101 SET NAMES utf8 */;

/*!40101 SET SQL_MODE=''*/;

/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
CREATE DATABASE /*!32312 IF NOT EXISTS*/`idataops_realtime_insights` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `idataops_realtime_insights`;

/*Table structure for table `actionable_insight` */

DROP TABLE IF EXISTS `actionable_insight`;

CREATE TABLE `actionable_insight` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `description` varchar(255) DEFAULT NULL,
  `description_text` text,
  `suggestion_text` text,
  `timestamp` datetime(6) DEFAULT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `aggregation_scheduler_checkpoint` */

DROP TABLE IF EXISTS `aggregation_scheduler_checkpoint`;

CREATE TABLE `aggregation_scheduler_checkpoint` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `aggregation_type` varchar(20) NOT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `timestamp` varchar(255) DEFAULT NULL,
  `equipment_id` varchar(36) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `UNIQUE_EQUIPMENT_AGGREGATION` (`equipment_id`,`aggregation_type`)
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `alert_configuration` */

DROP TABLE IF EXISTS `alert_configuration`;

CREATE TABLE `alert_configuration` (
  `id` char(36) NOT NULL,
  `goal_value` double NOT NULL,
  `variation` double NOT NULL,
  `alert_name` varchar(255) NOT NULL,
  `frequency_description` varchar(20) DEFAULT NULL,
  `frequency_duration` bigint DEFAULT NULL,
  `last_run` bigint NOT NULL,
  `next_run` bigint DEFAULT NULL,
  `query` text,
  `status` enum('FAIL','SUCCESS') NOT NULL,
  `type` enum('ALARM','SUMMARY') DEFAULT NULL,
  `value_table` varchar(255) DEFAULT NULL,
  `alarm_definition_id` char(36) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_on` datetime(6) NOT NULL,
  `created_by` varchar(50) NOT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `alert_distribution` */

DROP TABLE IF EXISTS `alert_distribution`;

CREATE TABLE `alert_distribution` (
  `id` char(36) NOT NULL,
  `alert_configuration_id` char(36) NOT NULL,
  `list_name` varchar(255) NOT NULL,
  `recipients` varchar(255) NOT NULL,
  `type` enum('MAIL','NOTIFICATION','SUMMARY_MAIL') NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_on` datetime(6) NOT NULL,
  `created_by` varchar(50) NOT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  `bcc_recipients` text,
  `cc_recipients` text,
  PRIMARY KEY (`id`),
  KEY `FK_ALERT_CONFIGURATION_ID` (`alert_configuration_id`),
  CONSTRAINT `FK_ALERT_CONFIGURATION_ID` FOREIGN KEY (`alert_configuration_id`) REFERENCES `alert_configuration` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `alert_log` */

DROP TABLE IF EXISTS `alert_log`;

CREATE TABLE `alert_log` (
  `id` char(36) NOT NULL,
  `equipment_id` char(36) DEFAULT NULL,
  `alert_configuration_id` char(36) NOT NULL,
  `last_successful_run` datetime(6) NOT NULL,
  `log_message` varchar(255) DEFAULT NULL,
  `status` enum('FAIL','SUCCESS','TRIGGERRED') DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_on` datetime(6) NOT NULL,
  `created_by` varchar(50) NOT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  `recipient_email_id` text,
  `facility_name` varchar(45) DEFAULT NULL,
  `report_type` enum('XLSX','PDF') DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_CONFIG_LOG` (`alert_configuration_id`),
  CONSTRAINT `FK_CONFIG_LOG` FOREIGN KEY (`alert_configuration_id`) REFERENCES `alert_configuration` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `app_metadata` */

DROP TABLE IF EXISTS `app_metadata`;

CREATE TABLE `app_metadata` (
  `id` int NOT NULL AUTO_INCREMENT,
  `property_key` varchar(255) NOT NULL,
  `type` varchar(45) NOT NULL,
  `property_value_string` text,
  `property_value_numeric` int DEFAULT NULL,
  `property_value_boolean` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `comparative_analysis_checkpoint` */

DROP TABLE IF EXISTS `comparative_analysis_checkpoint`;

CREATE TABLE `comparative_analysis_checkpoint` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `last_read` bigint DEFAULT NULL,
  `timestamp` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `d_date` */

DROP TABLE IF EXISTS `d_date`;

CREATE TABLE `d_date` (
  `date_id_key` int NOT NULL,
  `date_actual` date NOT NULL,
  `epoch` bigint NOT NULL,
  `day_suffix` varchar(4) NOT NULL,
  `day_name` varchar(9) NOT NULL,
  `day_of_week` int NOT NULL,
  `day_of_month` int NOT NULL,
  `day_of_quarter` int NOT NULL,
  `day_of_year` int NOT NULL,
  `week_of_month` int NOT NULL,
  `week_of_year` int NOT NULL,
  `month_actual` int NOT NULL,
  `month_name` varchar(9) NOT NULL,
  `month_name_abbreviated` varchar(3) NOT NULL,
  `quarter_actual` int NOT NULL,
  `quarter_name` varchar(9) NOT NULL,
  `year_actual` int NOT NULL,
  `first_day_of_week` date NOT NULL,
  `last_day_of_week` date NOT NULL,
  `yyyymm` varchar(6) NOT NULL,
  `yyyymmdd` varchar(10) NOT NULL,
  `is_weekend` tinyint(1) NOT NULL,
  `create_ts` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `create_by` varchar(100) NOT NULL DEFAULT 'SYSTEM',
  `update_ts` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_by` varchar(100) NOT NULL DEFAULT 'SYSTEM',
  PRIMARY KEY (`date_id_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `dashboard` */

DROP TABLE IF EXISTS `dashboard`;

CREATE TABLE `dashboard` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dashboard_layout` varchar(255) DEFAULT NULL,
  `user_id` varchar(255) DEFAULT NULL,
  `user_type` varchar(255) DEFAULT NULL,
  `dashboard_type` enum('RTUHEALTH','OVERVIEW','OEE','REPORTANALYTIC','PERFORMANCEMONITORING','PREDICTIVEMAINTENANCE','CONDITIONMONITORING','POWERUSAGEEFFECTIVENESS','WORKORDER','POWERANALYZER','SINGLEMACHINEVIEW','MANAGEMENTOVERVIEW','FACILITYDISPLAYBOARD','COMPARATIVEANALYSIS') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `active` bit(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `dashboard_row` */

DROP TABLE IF EXISTS `dashboard_row`;

CREATE TABLE `dashboard_row` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `label` varchar(255) DEFAULT NULL,
  `row_idx` int DEFAULT NULL,
  `dashboard_id` bigint NOT NULL,
  `active` bit(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK7c2etf8m7fy3a32a5cbdbewbf` (`dashboard_id`),
  CONSTRAINT `FK7c2etf8m7fy3a32a5cbdbewbf` FOREIGN KEY (`dashboard_id`) REFERENCES `dashboard` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=29 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `ddl_migration_history` */

DROP TABLE IF EXISTS `ddl_migration_history`;

CREATE TABLE `ddl_migration_history` (
  `installed_rank` int NOT NULL,
  `version` varchar(50) DEFAULT NULL,
  `description` varchar(200) NOT NULL,
  `type` varchar(20) NOT NULL,
  `script` varchar(1000) NOT NULL,
  `checksum` int DEFAULT NULL,
  `installed_by` varchar(100) NOT NULL,
  `installed_on` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `execution_time` int NOT NULL,
  `success` tinyint(1) NOT NULL,
  PRIMARY KEY (`installed_rank`),
  KEY `ddl_migration_history_s_idx` (`success`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `department` */

DROP TABLE IF EXISTS `department`;

CREATE TABLE `department` (
  `id` varchar(255) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `facility_id` char(15) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_FACILITY_ID` (`facility_id`),
  CONSTRAINT `FK_DEPARTMENT_FACILITY` FOREIGN KEY (`facility_id`) REFERENCES `facility` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `dml_migration_history` */

DROP TABLE IF EXISTS `dml_migration_history`;

CREATE TABLE `dml_migration_history` (
  `installed_rank` int NOT NULL,
  `version` varchar(50) DEFAULT NULL,
  `description` varchar(200) NOT NULL,
  `type` varchar(20) NOT NULL,
  `script` varchar(1000) NOT NULL,
  `checksum` int DEFAULT NULL,
  `installed_by` varchar(100) NOT NULL,
  `installed_on` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `execution_time` int NOT NULL,
  `success` tinyint(1) NOT NULL,
  PRIMARY KEY (`installed_rank`),
  KEY `dml_migration_history_s_idx` (`success`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment` */

DROP TABLE IF EXISTS `equipment`;

CREATE TABLE `equipment` (
  `id` char(36) NOT NULL,
  `name` varchar(128) DEFAULT NULL,
  `serial_no` varchar(45) NOT NULL,
  `model_no` varchar(16) NOT NULL,
  `purchase_date` datetime NOT NULL,
  `onboard_date` datetime NOT NULL,
  `onboard_type` varchar(10) NOT NULL,
  `source_type` varchar(3) NOT NULL,
  `datapoint` tinyint(1) DEFAULT '0',
  `image_ref` varchar(1023) DEFAULT NULL,
  `run_time` int DEFAULT NULL,
  `goal_part_count` bigint DEFAULT NULL,
  `goal_uptime_count` bigint DEFAULT NULL,
  `goal_oee_count` bigint DEFAULT NULL,
  `goal_uptime_pct` double DEFAULT NULL,
  `facility_id` char(15) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(45) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(45) DEFAULT NULL,
  `updated_on` datetime DEFAULT NULL,
  `description` text,
  `department_id` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `SERIAL_NO_UNIQUE` (`serial_no`),
  KEY `FK_FACILITY_ID_IDX` (`facility_id`),
  KEY `fk_equipment_department` (`department_id`),
  CONSTRAINT `fk_equipment_department` FOREIGN KEY (`department_id`) REFERENCES `department` (`id`) ON DELETE CASCADE,
  CONSTRAINT `FK_EQUIPMENT_FACILITY_ID` FOREIGN KEY (`facility_id`) REFERENCES `facility` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_alarm` */

DROP TABLE IF EXISTS `equipment_alarm`;

CREATE TABLE `equipment_alarm` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_name` varchar(50) NOT NULL,
  `end_time` varchar(50) NOT NULL,
  `equipment_id` char(36) NOT NULL,
  `start_time` varchar(50) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=258230 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_alarm_checkpoint` */

DROP TABLE IF EXISTS `equipment_alarm_checkpoint`;

CREATE TABLE `equipment_alarm_checkpoint` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `last_read` bigint DEFAULT NULL,
  `timestamp` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_checkpoint` */

DROP TABLE IF EXISTS `equipment_checkpoint`;

CREATE TABLE `equipment_checkpoint` (
  `machine_id` varchar(255) NOT NULL,
  `product_id` varchar(255) NOT NULL,
  `last_read` double DEFAULT NULL,
  `m5_group_name` datetime DEFAULT NULL,
  `np5m_max_value` double DEFAULT NULL,
  `np5m_total_value` double DEFAULT NULL,
  `ww5m_max_value` double DEFAULT NULL,
  `ww5m_total_value` double DEFAULT NULL,
  `jc5m_total_value` double DEFAULT NULL,
  `ut5m_max_value` double DEFAULT NULL,
  `ut5m_total_value` double DEFAULT NULL,
  `is_group_active` tinyint(1) DEFAULT '0',
  `ut5m_min_list` varchar(255) DEFAULT '[]',
  `last_minute_data_received` datetime DEFAULT NULL,
  PRIMARY KEY (`machine_id`,`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_checkpoint_pulse` */

DROP TABLE IF EXISTS `equipment_checkpoint_pulse`;

CREATE TABLE `equipment_checkpoint_pulse` (
  `machine_id` varchar(255) NOT NULL,
  `product_id` varchar(255) NOT NULL,
  `last_read` double DEFAULT NULL,
  `m5_group_name` datetime DEFAULT NULL,
  `np5m_max_value` double DEFAULT NULL,
  `np5m_total_value` double DEFAULT NULL,
  `ww5m_max_value` double DEFAULT NULL,
  `ww5m_total_value` double DEFAULT NULL,
  `jc5m_total_value` double DEFAULT NULL,
  `ut5m_max_value` double DEFAULT NULL,
  `ut5m_total_value` double DEFAULT NULL,
  `is_group_active` tinyint(1) DEFAULT '0',
  `ut5m_min_list` varchar(255) DEFAULT '[]',
  `last_minute_data_received` datetime DEFAULT NULL,
  PRIMARY KEY (`machine_id`,`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_comparative_analysis` */

DROP TABLE IF EXISTS `equipment_comparative_analysis`;

CREATE TABLE `equipment_comparative_analysis` (
  `equipment_id` char(36) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal` varchar(40) DEFAULT NULL,
  `part_count` varchar(40) DEFAULT NULL,
  `product_id` varchar(20) DEFAULT NULL,
  `uptime` varchar(40) DEFAULT NULL,
  `shift_type` varchar(20) NOT NULL,
  `bad_part` varchar(40) DEFAULT NULL,
  `goal_uptime` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`timestamp`,`shift_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data` */

DROP TABLE IF EXISTS `equipment_data`;

CREATE TABLE `equipment_data` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_id` varchar(255) DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_asset_date` (`equipment_id`,`timestamp`),
  KEY `index_asset_date` (`equipment_id`,`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=7577048 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_daily` */

DROP TABLE IF EXISTS `equipment_data_daily`;

CREATE TABLE `equipment_data_daily` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_datetime` */

DROP TABLE IF EXISTS `equipment_data_datetime`;

CREATE TABLE `equipment_data_datetime` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_id` char(36) NOT NULL,
  `timestamp` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_asset_date` (`equipment_id`,`timestamp`),
  KEY `index_asset_date` (`equipment_id`,`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=8326 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_hourly` */

DROP TABLE IF EXISTS `equipment_data_hourly`;

CREATE TABLE `equipment_data_hourly` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_metric` */

DROP TABLE IF EXISTS `equipment_data_metric`;

CREATE TABLE `equipment_data_metric` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_data_id` int DEFAULT NULL,
  `metric_key` varchar(255) DEFAULT NULL,
  `metric_value_string` text,
  `metric_value_numeric` decimal(10,0) DEFAULT NULL,
  `checkpoint` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_epd_key` (`equipment_data_id`,`metric_key`)
) ENGINE=InnoDB AUTO_INCREMENT=52168405 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_minute` */

DROP TABLE IF EXISTS `equipment_data_minute`;

CREATE TABLE `equipment_data_minute` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_monthly` */

DROP TABLE IF EXISTS `equipment_data_monthly`;

CREATE TABLE `equipment_data_monthly` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_quarterly` */

DROP TABLE IF EXISTS `equipment_data_quarterly`;

CREATE TABLE `equipment_data_quarterly` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_shift` */

DROP TABLE IF EXISTS `equipment_data_shift`;

CREATE TABLE `equipment_data_shift` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_data_id` bigint NOT NULL,
  `shift_id` varchar(20) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_Equipment_Data_Id_Shift_Id_idx` (`equipment_data_id`),
  KEY `FK_Shift_Data_Id_idx` (`shift_id`)
) ENGINE=InnoDB AUTO_INCREMENT=294883 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_timestamp` */

DROP TABLE IF EXISTS `equipment_data_timestamp`;

CREATE TABLE `equipment_data_timestamp` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_id` char(36) NOT NULL,
  `timestamp` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_asset_date` (`equipment_id`,`timestamp`),
  KEY `index_asset_date` (`equipment_id`,`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=8326 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_weekly` */

DROP TABLE IF EXISTS `equipment_data_weekly`;

CREATE TABLE `equipment_data_weekly` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_data_yearly` */

DROP TABLE IF EXISTS `equipment_data_yearly`;

CREATE TABLE `equipment_data_yearly` (
  `equipment_id` char(36) NOT NULL,
  `metric_key` varchar(40) NOT NULL,
  `product_id` varchar(20) NOT NULL,
  `shift_id` varchar(20) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `goal_value` decimal(38,2) DEFAULT '0.00',
  `metric_value` decimal(38,2) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`metric_key`,`product_id`,`shift_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_group` */

DROP TABLE IF EXISTS `equipment_group`;

CREATE TABLE `equipment_group` (
  `id` char(36) NOT NULL,
  `equipment_id` char(36) DEFAULT NULL,
  `group_id` char(36) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(45) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(45) DEFAULT NULL,
  `updated_on` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_EQUIPMENT_GROUP_EQUIPMENT_ID_IDX` (`equipment_id`),
  KEY `FK_EQUIPMENT_GROUP_GROUP_ID_IDX` (`group_id`),
  CONSTRAINT `FK_EQUIPMENT_GROUP_EQUIPMENT_ID` FOREIGN KEY (`equipment_id`) REFERENCES `equipment` (`id`),
  CONSTRAINT `FK_EQUIPMENT_GROUP_GROUP_ID` FOREIGN KEY (`group_id`) REFERENCES `group_table` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_product` */

DROP TABLE IF EXISTS `equipment_product`;

CREATE TABLE `equipment_product` (
  `product_name` varchar(50) NOT NULL,
  `product_id` varchar(50) NOT NULL,
  `cost` double DEFAULT '0',
  `equipment_id` char(36) NOT NULL,
  `timestamp` varchar(30) NOT NULL,
  PRIMARY KEY (`equipment_id`,`product_id`,`timestamp`,`product_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_product_goal` */

DROP TABLE IF EXISTS `equipment_product_goal`;

CREATE TABLE `equipment_product_goal` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `VIN` int NOT NULL,
  `item_id` varchar(50) DEFAULT NULL,
  `equipment_id` char(36) NOT NULL,
  `PPH` double DEFAULT NULL,
  `date` date NOT NULL,
  `status` varchar(20) DEFAULT NULL,
  `product_code` varchar(50) DEFAULT NULL,
  `description` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=105 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_status` */

DROP TABLE IF EXISTS `equipment_status`;

CREATE TABLE `equipment_status` (
  `equipment_id` varchar(50) NOT NULL,
  `timestamp` datetime NOT NULL,
  `status` varchar(255) DEFAULT NULL,
  `code` varchar(100) DEFAULT '',
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7588132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_status_alert_log` */

DROP TABLE IF EXISTS `equipment_status_alert_log`;

CREATE TABLE `equipment_status_alert_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_id` char(36) NOT NULL,
  `last_status` varchar(50) NOT NULL,
  `mail_status` varchar(50) NOT NULL,
  `recipient_email_id` varchar(255) DEFAULT NULL,
  `status_start_time` varchar(50) NOT NULL,
  `total_time` varchar(50) NOT NULL,
  `status_time` int DEFAULT '0',
  `mail_send_at` varchar(45) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=621 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `equipment_status_code` */

DROP TABLE IF EXISTS `equipment_status_code`;

CREATE TABLE `equipment_status_code` (
  `code` varchar(255) NOT NULL,
  `status` text,
  `id` int NOT NULL AUTO_INCREMENT,
  `short_status` text,
  `rgb_code` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=66 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `expenditures` */

DROP TABLE IF EXISTS `expenditures`;

CREATE TABLE `expenditures` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `cost_name` varchar(100) NOT NULL,
  `cost_value` double DEFAULT '0',
  `equipment_id` varchar(36) DEFAULT NULL,
  `type` enum('CAPEX','OPEX') DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(255) DEFAULT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(255) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_EQUIPMENT_ID_EXPEDITURES_IDX` (`equipment_id`),
  CONSTRAINT `FK_EQUIPMENT_ID_EXPEDITURES_IDX` FOREIGN KEY (`equipment_id`) REFERENCES `equipment` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `facility` */

DROP TABLE IF EXISTS `facility`;

CREATE TABLE `facility` (
  `id` char(15) NOT NULL,
  `name` varchar(45) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(45) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(45) DEFAULT NULL,
  `updated_on` datetime DEFAULT NULL,
  `is_live` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `NAME_UNIQUE` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `group_table` */

DROP TABLE IF EXISTS `group_table`;

CREATE TABLE `group_table` (
  `id` char(36) NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `description` varchar(1024) DEFAULT NULL,
  `facility_id` char(15) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(45) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(45) DEFAULT NULL,
  `updated_on` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name_UNIQUE` (`name`),
  KEY `FK_FACILITY_ID_GROUP_ID_IDX` (`facility_id`),
  CONSTRAINT `FK_FACILITY_ID_GROUP_ID` FOREIGN KEY (`facility_id`) REFERENCES `facility` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `hour_table` */

DROP TABLE IF EXISTS `hour_table`;

CREATE TABLE `hour_table` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `12h_format` int NOT NULL,
  `24h_format` varchar(5) NOT NULL,
  `suffix` varchar(2) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `inventory` */

DROP TABLE IF EXISTS `inventory`;

CREATE TABLE `inventory` (
  `id` varchar(36) NOT NULL,
  `product_id` varchar(50) DEFAULT NULL,
  `stock_quantity` double DEFAULT '0',
  `warehouse_name` varchar(70) DEFAULT NULL,
  `aging` varchar(50) DEFAULT NULL,
  `material_name` varchar(50) DEFAULT NULL,
  `max_stock_level` double DEFAULT '0',
  `min_required_stock` double DEFAULT '0',
  `stock_last_refresh_tmstmp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `machine_condition_speed` */

DROP TABLE IF EXISTS `machine_condition_speed`;

CREATE TABLE `machine_condition_speed` (
  `at_instance` bigint NOT NULL,
  `machine_uuid` char(36) NOT NULL,
  `speed` double NOT NULL,
  PRIMARY KEY (`at_instance`,`machine_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `machine_condition_temperature` */

DROP TABLE IF EXISTS `machine_condition_temperature`;

CREATE TABLE `machine_condition_temperature` (
  `at_instance` bigint NOT NULL,
  `machine_uuid` char(36) NOT NULL,
  `temperature` double NOT NULL,
  PRIMARY KEY (`at_instance`,`machine_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `machine_condition_torque` */

DROP TABLE IF EXISTS `machine_condition_torque`;

CREATE TABLE `machine_condition_torque` (
  `at_instance` bigint NOT NULL,
  `machine_uuid` char(36) NOT NULL,
  `torque` double NOT NULL,
  PRIMARY KEY (`at_instance`,`machine_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `machine_condition_vibration` */

DROP TABLE IF EXISTS `machine_condition_vibration`;

CREATE TABLE `machine_condition_vibration` (
  `at_instance` bigint NOT NULL,
  `machine_uuid` char(36) NOT NULL,
  `vibration` double NOT NULL,
  PRIMARY KEY (`at_instance`,`machine_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `machine_running_status` */

DROP TABLE IF EXISTS `machine_running_status`;

CREATE TABLE `machine_running_status` (
  `at_instance` bigint NOT NULL,
  `machine_uuid` char(36) NOT NULL,
  `availability` int NOT NULL,
  `end_instance` bigint NOT NULL,
  `machine_load` double NOT NULL,
  `performance` int NOT NULL,
  `quality` int NOT NULL,
  `status` varchar(255) DEFAULT NULL,
  `total_load` double NOT NULL,
  PRIMARY KEY (`at_instance`,`machine_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `mail_info` */

DROP TABLE IF EXISTS `mail_info`;

CREATE TABLE `mail_info` (
  `id` varchar(36) NOT NULL,
  `app_password` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `role_code` varchar(255) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_on` datetime(6) NOT NULL,
  `created_by` varchar(50) NOT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `mc_raw_data` */

DROP TABLE IF EXISTS `mc_raw_data`;

CREATE TABLE `mc_raw_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `asset_id` varchar(40) DEFAULT NULL,
  `connection_type` varchar(40) DEFAULT NULL,
  `customer_id` varchar(40) DEFAULT NULL,
  `data` text,
  `timestamp` bigint NOT NULL,
  `data_timestamp` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9242613 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `metrics_metadata` */

DROP TABLE IF EXISTS `metrics_metadata`;

CREATE TABLE `metrics_metadata` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `metric_data_key` varchar(70) NOT NULL,
  `description` varchar(250) DEFAULT NULL,
  `display_name` varchar(100) DEFAULT NULL,
  `data_type` varchar(50) DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  `metric_matadata_parent_id` bigint DEFAULT NULL,
  `i18n_key` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `metric_data_key` (`metric_data_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `minute_table` */

DROP TABLE IF EXISTS `minute_table`;

CREATE TABLE `minute_table` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `value` varchar(5) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=62 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `ocm_daily_alarm` */

DROP TABLE IF EXISTS `ocm_daily_alarm`;

CREATE TABLE `ocm_daily_alarm` (
  `date` datetime DEFAULT NULL,
  `alarm_name` text,
  `alarm_count` bigint DEFAULT NULL,
  `asset_id` text
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `ocm_down_time_by_alarm` */

DROP TABLE IF EXISTS `ocm_down_time_by_alarm`;

CREATE TABLE `ocm_down_time_by_alarm` (
  `alarm_name` text,
  `date` datetime DEFAULT NULL,
  `alarm_count` double DEFAULT NULL,
  `asset_id` text
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `ocm_product_details` */

DROP TABLE IF EXISTS `ocm_product_details`;

CREATE TABLE `ocm_product_details` (
  `product_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `component` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `usage` double DEFAULT NULL,
  `scrap` double DEFAULT NULL,
  `scrap_perc` bigint DEFAULT NULL,
  `unit` text,
  `total` double DEFAULT NULL,
  PRIMARY KEY (`product_id`,`component`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `operator` */

DROP TABLE IF EXISTS `operator`;

CREATE TABLE `operator` (
  `id` varchar(36) NOT NULL,
  `name` varchar(128) NOT NULL,
  `shift_count` int DEFAULT '0',
  `efficiency` double DEFAULT '0',
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `operator_duration` */

DROP TABLE IF EXISTS `operator_duration`;

CREATE TABLE `operator_duration` (
  `id` char(36) NOT NULL,
  `name` varchar(100) DEFAULT NULL,
  `duration` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `performance_monitoring` */

DROP TABLE IF EXISTS `performance_monitoring`;

CREATE TABLE `performance_monitoring` (
  `id` int NOT NULL AUTO_INCREMENT,
  `equipment_id` varchar(50) NOT NULL,
  `date` date DEFAULT NULL,
  `shift_id` int DEFAULT NULL,
  `status` enum('IDLE','RUNNING','HOMING_REQUIRED','OTHERS','SYSTEM_FAULT') DEFAULT NULL,
  `time_spend_mins` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=516 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `power_analyzer_table` */

DROP TABLE IF EXISTS `power_analyzer_table`;

CREATE TABLE `power_analyzer_table` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `current` float DEFAULT NULL,
  `energy` float DEFAULT NULL,
  `phase` varchar(255) DEFAULT NULL,
  `timestamp` bigint DEFAULT NULL,
  `voltage` float DEFAULT NULL,
  `wattage` float DEFAULT NULL,
  `equipment_id` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `power_data_cycle` */

DROP TABLE IF EXISTS `power_data_cycle`;

CREATE TABLE `power_data_cycle` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `equipment_id` char(36) NOT NULL,
  `cycle_name` varchar(30) NOT NULL,
  `operation_name` varchar(30) NOT NULL,
  `start_time` bigint NOT NULL,
  `end_time` bigint NOT NULL,
  `avg_wattage` float DEFAULT NULL,
  `avg_voltage` float DEFAULT NULL,
  `avg_current` float DEFAULT NULL,
  `avg_power_consumption` float DEFAULT NULL,
  `cumulative_power_consumption` float DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `power_data_daily` */

DROP TABLE IF EXISTS `power_data_daily`;

CREATE TABLE `power_data_daily` (
  `equipment_id` char(36) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `avg_wattage` float DEFAULT NULL,
  `avg_voltage` float DEFAULT NULL,
  `avg_current` float DEFAULT NULL,
  `avg_power_consumption` float DEFAULT NULL,
  `cumulative_power_consumption` float DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `power_data_hourly` */

DROP TABLE IF EXISTS `power_data_hourly`;

CREATE TABLE `power_data_hourly` (
  `equipment_id` char(36) NOT NULL,
  `timestamp` varchar(20) NOT NULL,
  `avg_wattage` float DEFAULT NULL,
  `avg_voltage` float DEFAULT NULL,
  `avg_current` float DEFAULT NULL,
  `avg_power_consumption` float DEFAULT NULL,
  `cumulative_power_consumption` float DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `quality_info` */

DROP TABLE IF EXISTS `quality_info`;

CREATE TABLE `quality_info` (
  `product_id` int NOT NULL,
  `bad_stock` int NOT NULL,
  `id` int NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `report_configuration` */

DROP TABLE IF EXISTS `report_configuration`;

CREATE TABLE `report_configuration` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `auto_run_enabled` tinyint(1) DEFAULT '1',
  `description` text,
  `last_executed_timestamp` datetime(6) DEFAULT NULL,
  `manual_execution_allowed` tinyint(1) DEFAULT '1',
  `report_name` varchar(255) NOT NULL,
  `template_name` varchar(255) NOT NULL,
  `type` varchar(200) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(255) NOT NULL,
  `created_on` datetime(6) NOT NULL,
  `updated_by` varchar(255) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `report_data` */

DROP TABLE IF EXISTS `report_data`;

CREATE TABLE `report_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `facility_name` varchar(50) DEFAULT NULL,
  `incharge` varchar(50) DEFAULT NULL,
  `shift_name` varchar(20) DEFAULT NULL,
  `supervisor` varchar(50) DEFAULT NULL,
  `facility_id` varchar(50) DEFAULT NULL,
  `shift_id` varchar(20) DEFAULT NULL,
  `machine_id` varchar(36) DEFAULT NULL,
  `machine_name` varchar(70) DEFAULT NULL,
  `operator` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=61 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `report_execution_summary` */

DROP TABLE IF EXISTS `report_execution_summary`;

CREATE TABLE `report_execution_summary` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `report_location` varchar(150) DEFAULT '',
  `report_storage_type` varchar(50) DEFAULT NULL,
  `report_type` enum('XLSX','PDF') DEFAULT NULL,
  `status` enum('CREATED','COMPLETED','INITIATED') DEFAULT NULL,
  `report_configuration_id` bigint DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime(6) NOT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `shift_id` bigint DEFAULT NULL,
  `facility_id` varchar(70) DEFAULT NULL,
  `facility_name` varchar(50) DEFAULT NULL,
  `report_date` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `UK_FACILITY_ID_REPORT_DATE` (`facility_id`,`report_date`,`report_type`),
  KEY `FK_REPORT_CONFIGURATION_ID_IDX` (`report_configuration_id`),
  CONSTRAINT `FK_REPORT_CONFIGURATION_ID_IDX` FOREIGN KEY (`report_configuration_id`) REFERENCES `report_configuration` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6901 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `rtu_equipment` */

DROP TABLE IF EXISTS `rtu_equipment`;

CREATE TABLE `rtu_equipment` (
  `equipment_id` varchar(255) NOT NULL,
  `rtu_id` varchar(255) NOT NULL,
  `last_com_timestamp` datetime(6) DEFAULT NULL,
  `last_status` enum('IDLE','OFFLINE','ONLINE','UNKNOWN') DEFAULT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`equipment_id`,`rtu_id`),
  KEY `FKqd6ij9cl1yc44voft7cd7e73u` (`rtu_id`),
  CONSTRAINT `FK_EQUIPMENT_RTU_ID` FOREIGN KEY (`rtu_id`) REFERENCES `rtu_registry` (`id`),
  CONSTRAINT `FK_RTU_EQUIPMENT_ID` FOREIGN KEY (`equipment_id`) REFERENCES `equipment` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `rtu_registry` */

DROP TABLE IF EXISTS `rtu_registry`;

CREATE TABLE `rtu_registry` (
  `id` varchar(255) NOT NULL,
  `ip_address` varchar(255) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `shift` */

DROP TABLE IF EXISTS `shift`;

CREATE TABLE `shift` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `start_time` time DEFAULT NULL,
  `end_time` time DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `shift_type` varchar(30) DEFAULT NULL,
  `shift_meta_data_id` bigint DEFAULT NULL,
  `date_id_key` int DEFAULT NULL,
  `department_id` varchar(255) DEFAULT NULL,
  `is_overnight` tinyint(1) DEFAULT '0',
  `working_hours` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_D_SHFIT_META_DATA_ID` (`shift_meta_data_id`),
  KEY `FK_D_DEPARTMENT_ID` (`department_id`),
  KEY `FK_D_DATE_ID` (`date_id_key`),
  CONSTRAINT `FK_D_DATE_ID` FOREIGN KEY (`date_id_key`) REFERENCES `d_date` (`date_id_key`),
  CONSTRAINT `FK_D_DEPARTMENT_ID` FOREIGN KEY (`department_id`) REFERENCES `department` (`id`),
  CONSTRAINT `FK_D_SHFIT_META_DATA_ID` FOREIGN KEY (`shift_meta_data_id`) REFERENCES `shift_meta_data` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=462 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `shift_break` */

DROP TABLE IF EXISTS `shift_break`;

CREATE TABLE `shift_break` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `shift_id` bigint NOT NULL,
  `break_start_time` time NOT NULL,
  `break_end_time` time NOT NULL,
  `break_type` varchar(50) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_SHIFT_ID` (`shift_id`),
  CONSTRAINT `FK_SHIFT_ID` FOREIGN KEY (`shift_id`) REFERENCES `shift` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `shift_duration` */

DROP TABLE IF EXISTS `shift_duration`;

CREATE TABLE `shift_duration` (
  `id` char(36) NOT NULL,
  `name` varchar(100) DEFAULT NULL,
  `duration` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `shift_meta_data` */

DROP TABLE IF EXISTS `shift_meta_data`;

CREATE TABLE `shift_meta_data` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `shift_key` varchar(20) NOT NULL,
  `shift_display_name` varchar(50) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `widget` */

DROP TABLE IF EXISTS `widget`;

CREATE TABLE `widget` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `col_index` int DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `dashboard_row_id` bigint DEFAULT NULL,
  `widget_configuration_id` bigint DEFAULT NULL,
  `template_key` varchar(255) DEFAULT NULL,
  `additional_properties` varchar(255) DEFAULT NULL,
  `active` bit(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK9foi6ji0oxwhxokmjvofaxoa` (`dashboard_row_id`),
  KEY `FK6hkutacxe0x4bxjlspdnisayn` (`widget_configuration_id`),
  CONSTRAINT `FK6hkutacxe0x4bxjlspdnisayn` FOREIGN KEY (`widget_configuration_id`) REFERENCES `widget_configuration` (`id`),
  CONSTRAINT `FK9foi6ji0oxwhxokmjvofaxoa` FOREIGN KEY (`dashboard_row_id`) REFERENCES `dashboard_row` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=82 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `widget_configuration` */

DROP TABLE IF EXISTS `widget_configuration`;

CREATE TABLE `widget_configuration` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `template_key` varchar(255) DEFAULT NULL,
  `version` varchar(255) DEFAULT NULL,
  `widget_name` varchar(255) DEFAULT NULL,
  `active` tinyint(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `UKssmgltqqvvp8vl6a7ylvf5ck5` (`widget_name`,`template_key`,`version`)
) ENGINE=InnoDB AUTO_INCREMENT=79 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `widget_query` */

DROP TABLE IF EXISTS `widget_query`;

CREATE TABLE `widget_query` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `query_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  `query_type` enum('CA','REST','SQL','SVC','SVC_BOM','RPA','MCM','PFM','PUE','PDM','WOD','DT','PA','SMV','MO','FDB','JOT','SSE') NOT NULL,
  `widget_configuration_id` bigint DEFAULT NULL,
  `active` bit(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `UK_dk87tlr2ntrbpextgbm3o3p9m` (`widget_configuration_id`),
  CONSTRAINT `FK59xr89hked8p4g21bthhux4hm` FOREIGN KEY (`widget_configuration_id`) REFERENCES `widget_configuration` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `widget_query_param` */

DROP TABLE IF EXISTS `widget_query_param`;

CREATE TABLE `widget_query_param` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `widget_query_id` bigint DEFAULT NULL,
  `param_name` varchar(255) DEFAULT NULL,
  `param_type` enum('Long','String') DEFAULT NULL,
  `param_value` varchar(255) DEFAULT NULL,
  `required` tinyint(1) DEFAULT '1',
  `active` bit(1) DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime(6) NOT NULL,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `UK8la24mirs152e0s76ljdgwxqi` (`widget_query_id`,`param_name`),
  CONSTRAINT `FK2s0ddmow9t104846tsmvdtnbm` FOREIGN KEY (`widget_query_id`) REFERENCES `widget_query` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*Table structure for table `work_order` */

DROP TABLE IF EXISTS `work_order`;

CREATE TABLE `work_order` (
  `id` char(36) NOT NULL,
  `equipment_id` varchar(36) DEFAULT NULL,
  `product_id` varchar(255) NOT NULL,
  `operator_id` varchar(255) DEFAULT NULL,
  `work_order_id` varchar(255) NOT NULL,
  `required_quantity` int NOT NULL,
  `scheduled_ref_no` varchar(255) DEFAULT NULL,
  `product_name` varchar(255) DEFAULT NULL,
  `status` enum('COMPLETED','IN_PROGRESS','TODO') DEFAULT 'TODO',
  `delivery_date` datetime(6) DEFAULT NULL,
  `planned_start_date` datetime(6) NOT NULL,
  `planned_completion_date` datetime(6) DEFAULT NULL,
  `actual_start_date` datetime(6) DEFAULT NULL,
  `actual_completion_date` datetime(6) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `created_by` varchar(50) NOT NULL,
  `created_on` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by` varchar(50) DEFAULT NULL,
  `updated_on` datetime(6) DEFAULT NULL,
  `completed_quantity` int DEFAULT '0',
  `balance_quantity` int DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `WORK_ORDER_EQUIPMENT_ID` (`equipment_id`),
  CONSTRAINT `FK_EQUIPMENT_ID` FOREIGN KEY (`equipment_id`) REFERENCES `equipment` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
