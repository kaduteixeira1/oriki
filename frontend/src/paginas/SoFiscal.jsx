import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { me } from "../api.js";
import { Carregando } from "../componentes.jsx";

// Fiscal e admin veem todos os pontos; o backend também confere o perfil em todas as rotas /api/fiscal.
export default function SoFiscal() {
  const [usuario, setUsuario] = useState(null);
  const [estado, setEstado] = useState("carregando");

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
  if (usuario.perfil === "batedor") return <Navigate to="/batedor" replace />;
  return <Outlet context={usuario} />;
}
