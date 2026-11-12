import { Link } from "react-router-dom";
import { BarraApp } from "../componentes.jsx";

export default function NaoEncontrado() {
  return (
    <main className="tela">
      <BarraApp />
      <div className="conteudo">
        <p className="aviso-centro">Página não encontrada.</p>
        <Link to="/" className="botao-secundario centro">Ir para o início</Link>
      </div>
    </main>
  );
}
