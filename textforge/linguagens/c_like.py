"""C, C++, C#, Java, Go e Rust: seis linguagens como DADOS.

Nenhuma classe nova. Todas sao instancias de `ProvedorGenerico`, parametrizadas por
listas de palavras. E' a demonstracao de que o requisito 36 funciona: acrescentar
Kotlin, Swift ou Dart aqui e' preencher uma tabela.

Onde uma linguagem tem particularidade que o generico nao cobre, ela ganha um
comentario dizendo qual e' a perda -- e' mais honesto que finger cobertura completa.
"""

from __future__ import annotations

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.generico import ProvedorGenerico

# Comum a todas as linguagens de chaves.
CHAVES = dict(
    comentario_de_linha="//",
    comentario_de_bloco=("/*", "*/"),
    modo_de_dobra="delimitadores",
    aumenta_indentacao=r"[{(\[]\s*$",
    diminui_indentacao=r"^\s*[})\]]",
)

C = ProvedorGenerico(
    nome="C",
    extensoes=(".c", ".h"),
    palavras_chave=(
        "auto break case char const continue default do double else enum extern "
        "float for goto if inline int long register restrict return short signed "
        "sizeof static struct switch typedef union unsigned void volatile while "
        "_Bool _Complex _Atomic").split(),
    # As diretivas do preprocessador entram como segunda familia, para terem cor
    # propria -- num .h elas sao metade do arquivo.
    palavras_chave_2=("#include #define #undef #ifdef #ifndef #if #else #elif "
                      "#endif #pragma #error #line").split(),
    tipos=("size_t ssize_t int8_t int16_t int32_t int64_t uint8_t uint16_t "
           "uint32_t uint64_t intptr_t uintptr_t ptrdiff_t wchar_t FILE").split(),
    constantes=("NULL true false EOF stdin stdout stderr").split(),
    prefixo_de_definicao=("struct", "union", "enum", "typedef"),
    indentacao=Indentacao(usa_espacos=True, largura=4),
    **CHAVES)

CPP = ProvedorGenerico(
    nome="C++",
    extensoes=(".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh", ".ipp", ".tpp"),
    palavras_chave=(
        "alignas alignof and asm auto bitand bitor bool break case catch char "
        "class compl concept const consteval constexpr constinit const_cast "
        "continue co_await co_return co_yield decltype default delete do double "
        "dynamic_cast else enum explicit export extern false float for friend "
        "goto if inline int long mutable namespace new noexcept not nullptr "
        "operator or private protected public register reinterpret_cast "
        "requires return short signed sizeof static static_assert static_cast "
        "struct switch template this thread_local throw true try typedef typeid "
        "typename union unsigned using virtual void volatile wchar_t while "
        "xor override final").split(),
    palavras_chave_2=("#include #define #undef #ifdef #ifndef #if #else #elif "
                      "#endif #pragma").split(),
    tipos=("size_t string wstring vector map unordered_map set unordered_set "
           "list deque array pair tuple shared_ptr unique_ptr weak_ptr optional "
           "variant function ostream istream stringstream int8_t int16_t "
           "int32_t int64_t uint8_t uint16_t uint32_t uint64_t").split(),
    constantes=("nullptr NULL true false std").split(),
    prefixo_de_definicao=("class", "struct", "namespace", "enum", "union",
                          "concept"),
    indentacao=Indentacao(usa_espacos=True, largura=4),
    **CHAVES)

CSHARP = ProvedorGenerico(
    nome="C#",
    extensoes=(".cs", ".csx"),
    palavras_chave=(
        "abstract as async await base bool break byte case catch char checked "
        "class const continue decimal default delegate do double dynamic else "
        "enum event explicit extern false finally fixed float for foreach get "
        "global goto if implicit in init int interface internal is lock long "
        "namespace new null object operator out override params partial private "
        "protected public readonly record ref return sbyte sealed set short "
        "sizeof stackalloc static string struct switch this throw true try "
        "typeof uint ulong unchecked unsafe ushort using value var virtual void "
        "volatile when where while yield nameof").split(),
    palavras_chave_2=("#region #endregion #if #else #elif #endif #define #undef "
                      "#pragma #nullable").split(),
    tipos=("List Dictionary IEnumerable IList ICollection Task Action Func "
           "Nullable DateTime TimeSpan Guid Exception StringBuilder Array "
           "HashSet Tuple Span Memory").split(),
    constantes=("true false null").split(),
    prefixo_de_definicao=("class", "struct", "interface", "enum", "record",
                          "namespace", "delegate"),
    indentacao=Indentacao(usa_espacos=True, largura=4),
    **CHAVES)

JAVA = ProvedorGenerico(
    nome="Java",
    extensoes=(".java", ".jsp", ".jspf"),
    palavras_chave=(
        "abstract assert boolean break byte case catch char class const continue "
        "default do double else enum extends final finally float for goto if "
        "implements import instanceof int interface long native new package "
        "private protected public return short static strictfp super switch "
        "synchronized this throw throws transient try var void volatile while "
        "record sealed permits yield").split(),
    tipos=("String Integer Long Double Float Boolean Character Byte Short "
           "Object List ArrayList Map HashMap Set HashSet Collection Optional "
           "Stream Exception RuntimeException Thread Runnable BigDecimal "
           "LocalDate LocalDateTime StringBuilder").split(),
    constantes=("true false null").split(),
    prefixo_de_definicao=("class", "interface", "enum", "record"),
    indentacao=Indentacao(usa_espacos=True, largura=4),
    **CHAVES)

GO = ProvedorGenerico(
    nome="Go",
    extensoes=(".go",),
    palavras_chave=(
        "break case chan const continue default defer else fallthrough for func "
        "go goto if import interface map package range return select struct "
        "switch type var").split(),
    tipos=("bool byte complex64 complex128 error float32 float64 int int8 int16 "
           "int32 int64 rune string uint uint8 uint16 uint32 uint64 uintptr "
           "any comparable").split(),
    constantes=("true false nil iota").split(),
    embutidas=("append cap close copy delete len make new panic print println "
               "recover min max clear").split(),
    prefixo_de_definicao=("func", "type"),
    # Go usa TAB por convencao -- e' o que o gofmt produz, e mudar isso num
    # arquivo Go seria contrariar a ferramenta oficial da linguagem.
    indentacao=Indentacao(usa_espacos=False, largura=4),
    **CHAVES)

RUST = ProvedorGenerico(
    nome="Rust",
    extensoes=(".rs",),
    palavras_chave=(
        "as async await break const continue crate dyn else enum extern false "
        "fn for if impl in let loop match mod move mut pub ref return self "
        "Self static struct super trait true type unsafe use where while union "
        "macro_rules").split(),
    tipos=("bool char f32 f64 i8 i16 i32 i64 i128 isize str u8 u16 u32 u64 "
           "u128 usize String Vec Option Result Box Rc Arc RefCell HashMap "
           "HashSet BTreeMap Cow").split(),
    constantes=("true false None Some Ok Err").split(),
    prefixo_de_definicao=("fn", "struct", "enum", "trait", "impl", "mod",
                          "type"),
    indentacao=Indentacao(usa_espacos=True, largura=4),
    **CHAVES)

# Perdas conhecidas do tratamento generico, escritas para ninguem descobrir por
# tentativa:
#   * C/C++: a string raw do C++11 (R"delim(...)delim") nao e' reconhecida como
#     um contexto proprio; ela e' pintada como string comum ate' a primeira aspa.
#   * Rust: a string raw (r#"..."#) tem o mesmo tratamento.
#   * Go: a string com crase (`...`), que atravessa linhas, nao vira contexto.
#   * Java/C#: a string de varias linhas ("""...""") tambem nao.
# Nenhuma dessas construcoes e' comum nos arquivos que este editor abre no dia a
# dia; quando for preciso, cada uma vira um `Contexto` no provedor especifico, sem
# tocar no motor.

PROVEDORES = (C, CPP, CSHARP, JAVA, GO, RUST)
