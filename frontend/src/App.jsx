import { Route, Routes } from "react-router-dom";
import RotaInicial from "./paginas/RotaInicial.jsx";
import Login from "./paginas/Login.jsx";
import SoBatedor from "./paginas/SoBatedor.jsx";
import HomeBatedor from "./paginas/HomeBatedor.jsx";
import FormularioLote from "./paginas/FormularioLote.jsx";
import Historico from "./paginas/Historico.jsx";
import Relatorio from "./paginas/Relatorio.jsx";
import QrDoPonto from "./paginas/QrDoPonto.jsx";
import Consumidor from "./paginas/Consumidor.jsx";
import Fiscal from "./paginas/Fiscal.jsx";
import SoFiscal from "./paginas/SoFiscal.jsx";
import DetalhePonto from "./paginas/DetalhePonto.jsx";
import NaoEncontrado from "./paginas/NaoEncontrado.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RotaInicial />} />
      <Route path="/login" element={<Login />} />
      <Route path="/batedor" element={<SoBatedor />}>
        <Route index element={<HomeBatedor />} />
        <Route path="lotes/:codigo" element={<FormularioLote />} />
        <Route path="historico" element={<Historico />} />
        <Route path="relatorio" element={<Relatorio />} />
        <Route path="qr" element={<QrDoPonto />} />
      </Route>
      <Route path="/p/:slug" element={<Consumidor />} />
      <Route path="/fiscal" element={<SoFiscal />}>
        <Route index element={<Fiscal />} />
        <Route path="pontos/:id" element={<DetalhePonto />} />
      </Route>
      <Route path="*" element={<NaoEncontrado />} />
    </Routes>
  );
}
