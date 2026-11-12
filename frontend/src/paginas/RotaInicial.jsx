import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { me } from "../api.js";
import { Carregando } from "../componentes.jsx";

export default function RotaInicial() {
  const [destino, setDestino] = useState(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    me()
      .then((usuario) => setDestino(usuario.perfil === "batedor" ? "/batedor" : "/fiscal"))
      .catch((erro) => (erro.status === 401 ? setDestino("/login") : setFalhou(true)));
  }, []);

  if (destino) return <Navigate to={destino} replace />;
  if (falhou) {
    return (
      <main className="tela">
        <p className="aviso-centro">Não foi possível conectar. Verifique a internet e tente de novo.</p>
        <button type="button" className="botao-secundario centro" onClick={() => window.location.reload()}>
          Tentar de novo
        </button>
      </main>
    );
  }
  return <Carregando />;
}
