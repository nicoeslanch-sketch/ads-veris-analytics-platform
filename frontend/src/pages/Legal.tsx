import { Link, useLocation } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { LEGAL_VERSION, PRIVACY_CONTROLLER, PRIVACY_EMAIL } from '../lib/privacy'

const privacy = [
  ['Responsable y contacto', `${PRIVACY_CONTROLLER} es responsable de los datos de registro, cuenta, soporte y operacion de ADS Veris. Puedes escribir a ${PRIVACY_EMAIL} para ejercer tus derechos o consultar sobre privacidad. Esta politica describe la operacion actual del servicio.`],
  ['Datos y finalidades', 'Usamos nombre, correo, empresa y pais para crear y administrar la cuenta; el telefono es opcional. La contrasena se gestiona con Supabase Auth y no se muestra al administrador. Cuando solicitas una prueba o un plan, podemos requerir un RUT de facturacion para validar la elegibilidad y evitar abuso. Tratamos archivos, configuraciones, resultados y preguntas para limpiar, estandarizar y analizar los datos que subes. Conservamos registros tecnicos y solicitudes para seguridad, diagnostico, soporte y ejercicio de derechos. No envies contrasenas, tarjetas, CVV ni datos de salud u otros datos especialmente sensibles.'],
  ['Datos de tus clientes y trabajadores', 'Debes tener autorizacion o una base legal aplicable para subir datos de terceros. En ese caso tu empresa determina la finalidad del analisis y ADS Veris procesa la informacion para prestar el servicio solicitado. Limita las columnas personales a las necesarias. La aceptacion de una cuenta no sustituye la autorizacion de las personas incluidas en un archivo. No uses la plataforma como unico repositorio de informacion importante.'],
  ['Consentimiento y comunicaciones', 'El formulario solicita una accion afirmativa, sin casillas premarcadas, para los datos de cuenta necesarios para el servicio. Guardamos la version aceptada y la fecha del servidor. No usamos esa aceptacion para publicidad. Puedes revocar el consentimiento por el apartado de privacidad o por correo; la revocacion no tiene efecto retroactivo y puede impedir mantener prestaciones que necesiten esos datos. Las comunicaciones de acceso, recuperacion de cuenta y soporte no son una suscripcion publicitaria.'],
  ['Proveedores y tratamiento fuera de Chile', 'Vercel aloja la interfaz; Render ejecuta el procesamiento; Supabase proporciona autenticacion, base de datos y almacenamiento. Estos proveedores pueden procesar informacion fuera de Chile. Si se habilitan funciones con un modelo externo, Anthropic puede recibir la pregunta y el contexto enviado para responderla; no confundas el asistente basado en reglas con una funcion de IA externa. Los cobros con tarjeta estan desactivados y la plataforma no solicita ni almacena datos de tarjeta. No vendemos tus archivos ni los publicamos como parte del servicio.'],
  ['Conservacion y eliminacion', 'Puedes borrar archivos desde Historial. La limpieza de Storage se activa al cargar archivos y aplica limites de cuenta y antiguedad; actualmente conserva los cinco archivos mas recientes y puede purgar otros tras 60 dias sin uso. No es una promesa de borrado automatico de toda la cuenta a los 60 dias. Los resultados, metadatos y registros pueden tener un ciclo distinto. Las solicitudes de privacidad quedan registradas para gestionarlas; pedir eliminacion no confirma que ya se haya ejecutado. Al responder una solicitud informaremos lo eliminado y cualquier conservacion necesaria por una obligacion legal o una disputa. Las copias de seguridad tienen un ciclo independiente y no deben restaurar datos suprimidos al servicio activo sin volver a aplicar las eliminaciones.'],
  ['Tus derechos', 'Puedes solicitar acceso, informacion sobre el uso y destinatarios, copia, rectificacion, eliminacion, bloqueo u oposicion segun la normativa aplicable. En Configuracion > Privacidad y datos puedes registrar y consultar una solicitud, sin pagar ni mejorar de plan. Tambien puedes escribir a servicios@adsveris.com si no tienes cuenta o no puedes entrar. Solo pediremos informacion proporcional para verificar tu identidad o representacion; no envies tu contrasena ni documentos de identidad por el chat. Una solicitud recibe un comprobante y una respuesta, no una promesa automatica de eliminacion inmediata.'],
  ['Seguridad y almacenamiento del navegador', 'Usamos conexiones HTTPS, controles de acceso por cuenta y protecciones para operaciones administrativas. Ningun sistema puede garantizar riesgo cero. El navegador guarda sesion y preferencias necesarias para el funcionamiento; cerrar sesion es importante en equipos compartidos. No se incluye publicidad ni seguimiento publicitario en esta version. Los proveedores de infraestructura pueden generar registros tecnicos para operar y proteger el servicio.'],
  ['Cambios y alcance', 'La politica se identifica por version. No presumimos aceptaciones de usuarios antiguos ni cambiamos silenciosamente la fecha de una aceptacion. Los cambios relevantes de finalidad requieren informacion y, cuando corresponda, nueva autorizacion. Esta politica no reemplaza los contratos de tratamiento con empresas ni la revision de obligaciones segun los paises donde se ofrezca el servicio.'],
]
const terms = [
  ['Servicio', 'ADS Veris SpA ofrece herramientas de limpieza, estandarizacion, exploracion y analisis. Los resultados dependen de la calidad y estructura de los archivos. Las relaciones por ID, monedas, duplicados y formulas requieren revision cuando el sistema informa ambiguedades. El servicio no certifica estados financieros ni reemplaza asesoria contable, tributaria, legal o financiera profesional.'],
  ['Cuenta y archivos', 'La cuenta inicial corresponde a un usuario responsable de una empresa. No compartas credenciales. Debes estar autorizado para usar los archivos y las fuentes conectadas; conservas tus derechos sobre ellos. No subas contenido ilicito, secretos de acceso ni datos que no sean necesarios. No se permite intentar acceder a otras cuentas, evadir limites o interrumpir el servicio.'],
  ['Planes y ADS Coins', 'Los limites de almacenamiento, archivos y funciones se muestran en la cuenta. ADS Coins son creditos de servicio, no dinero, inversion ni saldo bancario: no se pueden retirar ni se les atribuye una equivalencia fija en pesos. Los cobros y compras estan desactivados. Una futura compra requerira informar antes de confirmar su precio total, impuestos, prestaciones, vigencia, renovacion, cancelacion y devoluciones. No se realiza una renovacion pagada sin autorizacion.'],
  ['Resultados y disponibilidad', 'Descarga y revisa los resultados antes de decisiones importantes. El asistente puede equivocarse y debe distinguir datos publicados de estimaciones. No se garantiza disponibilidad continua ni capacidad ilimitada; trabajos pesados pueden esperar en cola. Estos limites no excluyen derechos irrenunciables ni obligaciones legales del proveedor.'],
  ['Privacidad, cierre y soporte', 'Puedes borrar archivos y solicitar el cierre de la cuenta desde Configuracion > Privacidad y datos, o escribir a servicios@adsveris.com. Se informara el resultado y cualquier conservacion legal necesaria. La politica de privacidad forma parte de la informacion del servicio. Las controversias y derechos se rigen por la normativa que resulte aplicable, sin renuncia anticipada de derechos del usuario.'],
]

export default function Legal() {
  const path = useLocation().pathname
  const isPrivacy = path === '/privacidad'
  const isLicenses = path === '/licencias'
  return <main className="min-h-screen bg-white px-5 py-8 text-navy sm:px-8">
    <div className="mx-auto max-w-3xl">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-teal"><ArrowLeft className="h-4 w-4" /> ADS Veris</Link>
      <h1 className="mt-6 text-2xl font-bold">{isLicenses ? 'Licencias y atribuciones' : isPrivacy ? 'Politica de privacidad' : 'Condiciones de uso'}</h1>
      <p className="mt-2 text-sm text-navy/60">{PRIVACY_CONTROLLER} · Version {LEGAL_VERSION}</p>
      <nav aria-label="Documentos legales" className="my-6 flex flex-wrap gap-4 border-y border-navy/15 py-3 text-sm text-teal">
        <Link to="/privacidad">Privacidad</Link><Link to="/condiciones">Condiciones</Link><Link to="/licencias">Licencias</Link>
      </nav>
      {isLicenses ? <div className="space-y-5 text-sm leading-7">
        <p>La tipografia Poppins se distribuye bajo SIL Open Font License 1.1 y se sirve desde esta aplicacion, sin consultar Google Fonts.</p>
        <p>Los iconos Lucide se distribuyen bajo ISC, con partes de Feather bajo MIT. Las licencias y avisos de las dependencias distribuidas se conservan en el archivo siguiente.</p>
        <a className="text-teal underline" href="/THIRD_PARTY_NOTICES.txt">Licencias completas de terceros</a>
        <p>Esta version no incluye fotografias de stock. El favicon es un recurso del proyecto. Estas atribuciones no otorgan derechos sobre marcas ni sobre los archivos que suben los usuarios.</p>
      </div> : (isPrivacy ? privacy : terms).map(([title, content]) => <section key={title} className="my-6">
        <h2 className="text-base font-semibold">{title}</h2><p className="mt-2 text-sm leading-7 text-navy/80">{content}</p>
      </section>)}
      <footer className="mt-8 border-t border-navy/15 pt-5 text-sm"><a className="text-teal underline" href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a></footer>
    </div>
  </main>
}
