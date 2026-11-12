import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { aceitarTermo, me } from "../api.js";
import { BarraApp, BotaoSair, Carregando } from "../componentes.jsx";

export default function SoBatedor() {
  const [usuario, setUsuario] = useState(null);
  const [estado, setEstado] = useState("carregando"); // carregando | ok | sem_sessao | falhou

  useEffect(() => {
    me()
      .then((dados) => {
        setUsuario(dados);
        setEstado("ok");
      })
      .catch((erro) => setEstado(erro.status === 401 ? "sem_sessao" : "falhou"));
  }, []);

  if (estado === "carregando") return <Carregando />;
  if (estado === "sem_sessao") return <Navigate to="/login" replace />;
  if (estado === "falhou") {
    return <p className="aviso-centro">Não foi possível conectar. Verifique a internet e tente de novo.</p>;
  }
  if (usuario.perfil !== "batedor") {
    return (
      <main className="tela">
        <BarraApp acao={<BotaoSair />} />
        <p className="aviso-centro">Esta área é do batedor.</p>
      </main>
    );
  }
  if (!usuario.termo_aceito) {
    return <Termo aoAceitar={() => setUsuario({ ...usuario, termo_aceito: true })} />;
  }
  return <Outlet context={usuario} />;
}

// O backend responde 403 termo_pendente nas rotas do batedor até o aceite (seção 10.3 do plano).
function Termo({ aoAceitar }) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  async function aceitar() {
    setEnviando(true);
    setErro("");
    try {
      await aceitarTermo();
      aoAceitar();
    } catch {
      setErro("Não foi possível registrar o aceite. Tente de novo.");
      setEnviando(false);
    }
  }

  return (
    <main className="tela">
      <BarraApp acao={<BotaoSair />} />
      <div className="conteudo">
        <section className="card">
          <h2 className="titulo-card">Termo de uso</h2>
          {/* F5: texto definitivo a redigir e revisar com a orientação (seção 17 do plano). */}
          <p className="texto-pequeno">Texto provisório.</p>
          <p>
            O Oriki guarda os registros de branqueamento do seu ponto, medidos pelo dispositivo no tanque, e
            os dados que você informa em cada lote. A fiscalização pode consultar esses registros, e a página do
            QR mostra o resumo do ponto, sem o seu nome ou e-mail.
          </p>
          <p>Você pode pedir a exclusão dos seus dados pessoais a qualquer momento.</p>
          {erro && <p className="erro-formulario" role="alert">{erro}</p>}
          <button type="button" className="botao-principal" onClick={aceitar} disabled={enviando}>
            Li e aceito
          </button>
        </section>
      </div>
    </main>
  );
}
