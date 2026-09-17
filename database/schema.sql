CREATE TABLE usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    senha_hash      TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('candidato', 'instrutor')),
    cidade          TEXT,
    telefone        TEXT,
    foto_url        TEXT,
    data_cadastro   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE perfis_acessibilidade (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id                  INTEGER NOT NULL UNIQUE,
    tipo_deficiencia            TEXT,
    canal_comunicacao           TEXT CHECK (canal_comunicacao IN ('texto', 'libras', 'audio')),
    precisa_veiculo_adaptado    INTEGER NOT NULL DEFAULT 0 CHECK (precisa_veiculo_adaptado IN (0, 1)),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
);

CREATE TABLE instrutores (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id                  INTEGER NOT NULL UNIQUE,
    categorias_cnh              TEXT NOT NULL,
    valor_aula                  REAL NOT NULL,
    regiao_atuacao              TEXT,
    verificado                  INTEGER NOT NULL DEFAULT 0 CHECK (verificado IN (0, 1)),
    atende_libras               INTEGER NOT NULL DEFAULT 0 CHECK (atende_libras IN (0, 1)),
    somente_mulheres            INTEGER NOT NULL DEFAULT 0 CHECK (somente_mulheres IN (0, 1)),
    atende_neurodivergentes     INTEGER NOT NULL DEFAULT 0 CHECK (atende_neurodivergentes IN (0, 1)),
    atende_pcd                  INTEGER NOT NULL DEFAULT 0 CHECK (atende_pcd IN (0, 1)),
    veiculo_adaptado_disponivel INTEGER NOT NULL DEFAULT 0 CHECK (veiculo_adaptado_disponivel IN (0, 1)),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
);

CREATE TABLE preferencias_candidato (
    id                                      INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id                              INTEGER NOT NULL UNIQUE,
    categorias_cnh_pretendidas              TEXT NOT NULL,
    prefere_instrutoras_mulheres            INTEGER NOT NULL DEFAULT 0 CHECK (prefere_instrutoras_mulheres IN (0, 1)),
    prefere_experiencia_neurodivergencia    INTEGER NOT NULL DEFAULT 0 CHECK (prefere_experiencia_neurodivergencia IN (0, 1)),
    prefere_experiencia_pcd                 INTEGER NOT NULL DEFAULT 0 CHECK (prefere_experiencia_pcd IN (0, 1)),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
);

CREATE TABLE veiculos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    marca           TEXT NOT NULL,
    modelo          TEXT NOT NULL,
    categoria_cnh   TEXT NOT NULL CHECK (categoria_cnh IN ('A', 'B', 'C', 'D', 'E')),
    transmissao     TEXT NOT NULL CHECK (transmissao IN ('manual', 'automatico')),
    adaptado        INTEGER NOT NULL DEFAULT 0 CHECK (adaptado IN (0, 1)),
    valor_locacao   REAL NOT NULL,
    imagem          TEXT NOT NULL
);

CREATE TABLE instrutor_veiculos (
    instrutor_id    INTEGER NOT NULL,
    veiculo_id      INTEGER NOT NULL,
    PRIMARY KEY (instrutor_id, veiculo_id),
    FOREIGN KEY (instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE,
    FOREIGN KEY (veiculo_id) REFERENCES veiculos (id) ON DELETE CASCADE
);

CREATE TABLE agendamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id    INTEGER NOT NULL,
    instrutor_id    INTEGER NOT NULL,
    veiculo_id      INTEGER,
    data            TEXT NOT NULL,
    horario         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'agendado' CHECK (status IN ('agendado', 'confirmado', 'concluido', 'cancelado')),
    valor           REAL NOT NULL,
    valor_locacao   REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (candidato_id) REFERENCES usuarios (id),
    FOREIGN KEY (instrutor_id) REFERENCES instrutores (id),
    FOREIGN KEY (veiculo_id) REFERENCES veiculos (id)
);

CREATE TABLE avaliacoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agendamento_id  INTEGER NOT NULL UNIQUE,
    candidato_id    INTEGER NOT NULL,
    instrutor_id    INTEGER NOT NULL,
    nota            INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario      TEXT,
    data            TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agendamento_id) REFERENCES agendamentos (id) ON DELETE CASCADE,
    FOREIGN KEY (candidato_id) REFERENCES usuarios (id),
    FOREIGN KEY (instrutor_id) REFERENCES instrutores (id)
);

CREATE INDEX idx_instrutores_usuario ON instrutores (usuario_id);
CREATE INDEX idx_instrutor_veiculos_veiculo ON instrutor_veiculos (veiculo_id);
CREATE INDEX idx_agendamentos_instrutor ON agendamentos (instrutor_id);
CREATE INDEX idx_agendamentos_candidato ON agendamentos (candidato_id);
CREATE INDEX idx_avaliacoes_instrutor ON avaliacoes (instrutor_id);
