import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { URL_QR } from "../api.js";
import { BarraApp } from "../componentes.jsx";

export default function QrDoPonto() {
  const { estabelecimento } = useOutletContext();
  const [falhou, setFalhou] = useState(false);

  return (
    <main className="tela">
      <BarraApp titulo="QR do ponto" voltarPara="/batedor" />
      <div className="conteudo">
        <section className="card cartaz-qr">
          <p className="titulo-card">{estabelecimento.nome}</p>
          {falhou ? (
            <p className="aviso-centro">Não foi possível carregar o QR. Verifique a internet e tente de novo.</p>
          ) : (
            <img src={URL_QR} className="imagem-qr" onError={() => setFalhou(true)}
                 alt={`QR que abre a página pública de ${estabelecimento.nome}`} />
          )}
          <p className="texto-pequeno">Escaneie para ver os registros do branqueamento deste ponto.</p>
        </section>
        <p className="texto-pequeno texto-2 nao-imprimir">
          Cole na vitrine. Quem escanear vê a licença e os ciclos dos últimos 7 dias, sem instalar nada e sem ver
          dados pessoais seus.
        </p>
        <button type="button" className="botao-principal nao-imprimir" onClick={() => window.print()} disabled={falhou}>
          Imprimir
        </button>
        <a href={URL_QR} download={`qr-${estabelecimento.slug_qr}.svg`} className="botao-secundario centro nao-imprimir">
          Baixar arquivo
        </a>
      </div>
    </main>
  );
}
