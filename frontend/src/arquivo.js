// Salva um arquivo gerado pela API (PDF) no aparelho, pela pasta de downloads do navegador.
export function salvarNoAparelho(blob, nome) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
