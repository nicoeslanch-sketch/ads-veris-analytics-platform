-- Fase 14c: ciclo de vida de la identidad de facturación.
--
-- Una solicitud de contratación o un trial histórico no deben impedir que el
-- equipo atienda una petición de eliminación de la identidad reutilizable.
-- Las referencias quedan nulas; account_trials conserva la evidencia
-- antiabuso (rut_normalized) y, por tanto, eliminar la identidad no habilita
-- una segunda prueba gratuita.

begin;

alter table public.addon_requests
  drop constraint if exists addon_requests_billing_identity_id_fkey;

alter table public.addon_requests
  add constraint addon_requests_billing_identity_id_fkey
  foreign key (billing_identity_id)
  references public.billing_identities (id)
  on delete set null;

alter table public.account_trials
  alter column billing_identity_id drop not null;

alter table public.account_trials
  drop constraint if exists account_trials_billing_identity_id_fkey;

alter table public.account_trials
  add constraint account_trials_billing_identity_id_fkey
  foreign key (billing_identity_id)
  references public.billing_identities (id)
  on delete set null;

comment on column public.account_trials.billing_identity_id is
  'Referencia opcional a la identidad reutilizable; queda NULL si se elimina. El RUT del trial se conserva para prevenir reactivaciones.';

commit;
