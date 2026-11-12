import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api.js";
import { semConexao } from "../fila.js";
import { BotaoLayout } from "../layout.jsx";

function mensagemDeErro(erro) {
  if (erro.status === 401) return "E-mail ou senha incorretos.";
  if (erro.status === 429) return "Muitas tentativas. Espere 1 minuto.";
  if (semConexao(erro)) return "Sem internet. Conecte-se para entrar.";
  return "Não foi possível entrar. Tente de novo.";
}

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  async function entrar(evento) {
    evento.preventDefault();
    setEnviando(true);
    setErro("");
    try {
      await login(email, senha);
      navigate("/", { replace: true });
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  }

  return (
    <main className="tela tela-login">
      <BotaoLayout className="botao-secundario botao-layout-login" />
      <div className="cartao-login">
      <p className="marca-login">Oriki</p>
      <p className="subtitulo-login">Registro do branqueamento do açaí</p>
      <form className="formulario" onSubmit={entrar} noValidate>
        <label className="campo">
          <span className="rotulo">E-mail</span>
          <input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="campo">
          <span className="rotulo">Senha</span>
          <input type="password" autoComplete="current-password" required value={senha}
                 onChange={(e) => setSenha(e.target.value)} />
        </label>
        {erro && <p className="erro-formulario" role="alert">{erro}</p>}
        <button type="submit" className="botao-principal" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
      <p className="texto-pequeno texto-2 dica-login">
        Consumidor não precisa entrar: escaneie o QR na vitrine do ponto.
      </p>
      </div>
    </main>
  );
}
