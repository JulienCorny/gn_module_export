SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;
--
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS gn_exports;

SET search_path = gn_exports, pg_catalog;
SET default_tablespace = '';
SET default_with_oids = false;


DROP TABLE IF EXISTS gn_exports.cor_role_export;
CREATE TABLE cor_role_export (
    id_cor_role_export SERIAL NOT NULL,
    roles character(255),
    CONSTRAINT pk_cor_role_export PRIMARY KEY (id_cor_role_export)
);


DROP TABLE IF EXISTS gn_exports.t_exports;
CREATE TABLE gn_exports.t_exports (
  id SERIAL NOT NULL,
  label text COLLATE pg_catalog."default" NOT NULL,
  selection text COLLATE pg_catalog."default" NOT NULL,
  CONSTRAINT pk_t_exports PRIMARY KEY (id)
);

DROP TABLE IF EXISTS gn_exports.t_exports_logs;
CREATE TABLE gn_exports.t_exports_logs (
    id TIMESTAMP NOT NULL,
    start date,
    "end" date,
    format integer NOT NULL,
    status numeric DEFAULT '-2'::integer,
    log text COLLATE pg_catalog."default",
    id_export integer,
    id_role integer,
    CONSTRAINT pk_t_exports_logs PRIMARY KEY (id),
    CONSTRAINT fk_export_type_selection FOREIGN KEY (id_export)
      REFERENCES gn_exports.t_exports (id) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE NO ACTION,
    CONSTRAINT fk_cor_role_exports_t_export_logs FOREIGN KEY (id_role)
      REFERENCES gn_exports.cor_role_export (id_cor_role_export) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE NO ACTION
);
