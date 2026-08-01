-- 0023 - Roles genéricos para consolidar cualquier Excel o CSV.
-- ADITIVA Y RETROCOMPATIBLE: conserva todos los roles DEMRE existentes.

begin;

alter table public.consolidation_project_sources
  drop constraint if exists consolidation_project_sources_role_check;

alter table public.consolidation_project_sources
  add constraint consolidation_project_sources_role_check
  check (role in (
    'primary','supplement_1','supplement_2','supplement_3','supplement_4',
    'equivalence_1','equivalence_2','historical',
    'matricula','archivo_b','archivo_c','archivo_d','oferta','historica',
    'codebook_matricula','codebook_b','codebook_c','codebook_d'
  ));

commit;
