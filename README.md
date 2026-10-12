# on2uml

OWL 온톨로지(Turtle `.ttl`)를 UML 클래스 다이어그램 이미지로 바꾼다. 보고서와 설계 문서에 넣을 그림을 TTL에서 바로 뽑는 것이 목적이다. TTL이 원본이고 그림은 매번 다시 생성하므로, TTL을 고치면 그림도 같은 명령 한 줄로 따라온다.

![예제](docs/example.png)

만들 수 있는 그림은 세 종류다.

- **보고용 뷰**: 개요, 특정 클래스 중심 그림처럼 직접 고른 그림 몇 장
- **클래스별 상세 그림**: 모든 클래스에 한 장씩. 다시 생성하면 어떤 그림이 바뀌었는지 알려 준다
- **버전 비교 그림**: 이전 TTL 대비 추가·변경·삭제를 색으로 표시

렌더링은 로컬 PlantUML로 한다. 온톨로지가 외부 서버로 나가지 않는다.

## 1. 설치

필요한 것은 [uv](https://docs.astral.sh/uv/), Java 11 이상, Graphviz, PlantUML jar다.

```bash
git clone https://github.com/Gaebobman/on2uml.git
cd on2uml
uv sync

# Graphviz
brew install graphviz            # Ubuntu: sudo apt install graphviz

# PlantUML jar (버전 고정)
mkdir -p ~/.local/share/plantuml
curl -L -o ~/.local/share/plantuml/plantuml.jar \
  https://github.com/plantuml/plantuml/releases/download/v1.2024.7/plantuml-1.2024.7.jar
echo 'export PLANTUML_JAR=~/.local/share/plantuml/plantuml.jar' >> ~/.zshrc   # bash면 ~/.bashrc
source ~/.zshrc
```

설치를 확인한다. 둘 다 오류 없이 끝나면 된다.

```bash
java -jar "$PLANTUML_JAR" -testdot      # "Installation seems OK" 가 나와야 함
uv run on2uml examples/vehicle.ttl -o out/test.png --focus Vehicle
open out/test.png                        # Linux: xdg-open
```

## 2. 내 TTL로 첫 그림 뽑기

클래스 하나를 중심으로 그리는 게 가장 빠르다. 클래스는 로컬 이름(`Truck`), `rdfs:label`(`트럭`), 전체 IRI 중 아무것으로나 지정한다.

```bash
uv run on2uml path/to/ontology.ttl -o out/truck.png --focus Truck
```

전체를 한 장에 그리면 클래스가 수십 개만 넘어도 너무 넓어져서 읽을 수 없다. 전체 그림이 필요하면 말단 클래스를 부모 박스 안에 접는다.

```bash
uv run on2uml path/to/ontology.ttl -o out/overview.png \
  --collapse 3 --no-attributes --names label --notes none --direction lr
```

## 3. 정기 작업 세팅: `views.yaml`

매번 같은 그림 세트를 뽑는다면 명령 대신 설정 파일을 하나 만든다. `examples/views.yaml`을 TTL 옆에 복사해서 고치는 게 가장 쉽다.

```yaml
ontology: ontology.ttl          # 이 파일 기준 상대 경로
output_dir: out

defaults:                       # 모든 그림에 공통 적용
  collapse: 3

views:                          # 보고용 뷰 (원하는 만큼)
  - name: overview              # -> out/overview.png
    title: 도메인 개요
    names: label
    notes: none
    attributes: false
    direction: lr
  - name: truck
    focus: Truck

per_class:                      # 모든 클래스 상세 그림
  classes: all                  # all | domain (표준 온톨로지 클래스 제외) | [Class, ...]
  output_dir: out/classes
  individuals: true
```

```bash
uv run on2uml --config path/to/views.yaml                  # 전부
uv run on2uml --config path/to/views.yaml --only overview  # 일부만 (per_class도 이름으로 지정 가능)
```

뷰에 쓰는 키는 CLI 옵션과 같다(`--color-by` → `color_by`). 키 이름을 잘못 쓰면 바로 오류가 난다. 전체 키 목록은 [Reference](#reference)에 있다.

## 4. TTL을 고친 뒤

같은 명령을 다시 실행하면 된다. 클래스별 그림은 바뀐 것만 다시 렌더링하고, 결과를 이렇게 알려 준다. 아래는 예제에서 `Motorcycle`을 지우고 `Bus`에 속성을 하나 추가한 뒤 다시 실행한 결과다.

```text
[per_class] out/classes  (added 0, changed 2, removed 1, unchanged 5)
  changed: Bus, Vehicle
  removed: Motorcycle
```

`out/classes/`에는 이런 파일이 생긴다.

| 파일 | 용도 |
|---|---|
| `<클래스>.png` | 문서에 넣을 그림 |
| `<클래스>.puml` | 그림의 텍스트 원본. Git에 넣으면 `git diff`로 무엇이 바뀌었는지 줄 단위로 보인다 |
| `index.md` | 전체 그림 목록, 마지막 생성에서 바뀐 그림 목록 |
| `manifest.json` | 클래스별 해시. 다음 실행 때 변경을 판단하는 기준이다 |

변경은 클래스 단위가 아니라 그림 단위로 센다. 상위 클래스에 속성을 하나 추가하면, 그 속성을 상속해서 보여 주는 하위 클래스 그림도 같이 "변경"으로 잡힌다. 삭제된 클래스의 그림은 자동으로 지워진다.

TTL과 같은 저장소에 `views.yaml`과 `out/`을 함께 커밋하면 "어떤 TTL 수정이 어떤 그림을 바꿨는지"가 커밋 단위로 남는다.

### 이전 버전과 비교한 그림

변경 내용을 그림으로 보여 주려면 이전 TTL을 지정한다. 추가된 클래스는 초록, 변경된 클래스는 주황, 삭제된 클래스는 회색 점선, 새 관계는 초록 굵은 화살표로 그린다.

```bash
git show v1.2:ontology.ttl > /tmp/ontology_v1.2.ttl
uv run on2uml ontology.ttl -o out/changes.png --compare /tmp/ontology_v1.2.ttl --focus Vehicle
```

`views.yaml`에서는 최상위에 `compare: <이전 TTL 경로>`를 쓴다. 비교가 필요 없는 뷰와 `per_class`에는 `compare: false`를 준다. 비교가 켜져 있으면 모든 그림에 비교 색과 범례가 들어간다.

## 그림 읽는 법

그림마다 오른쪽 아래에 범례가 붙는다. 범례에는 그 그림에 실제로 나온 기호만 적힌다. 범례를 빼려면 `--no-legend`(`views.yaml`에서는 `legend: false`)를 쓴다. 전체 기호는 아래와 같다.

| TTL | 그림 |
|---|---|
| `owl:Class` | 클래스 박스. `rdfs:label`과 로컬 이름을 함께 표시 |
| `rdfs:subClassOf` | 자식 ──▷ 부모. 빈 삼각형이 있는 쪽이 상위 클래스 |
| `owl:DatatypeProperty` | domain 클래스 박스 안의 속성 줄 `이름 : 타입` |
| `owl:ObjectProperty` | domain ──> range. 화살표 위 글자가 관계 이름 |
| `owl:Restriction` | 화살표 끝의 숫자는 range 쪽 개수(`1..*` 1개 이상, `0..2` 최대 2개). `«only»`는 그 클래스만 올 수 있다는 뜻. 속성 줄에서는 `[1..*]`, `= 값` |
| `owl:equivalentClass` | `≡` 점선 |
| `owl:NamedIndividual` | 객체 박스와 `«instanceOf»` 점선 (`--individuals`) |
| `rdfs:comment`, `skos:definition` | 노란 노트. 기본으로 `--focus` 클래스에만 붙는다 |
| BFO, IOF 같은 표준 온톨로지 클래스 | `«BFO»`, `«IOF»` 표시와 회색 배경. 범례에 표준 이름 |
| 보라색 점선 화살표 | 그림에 없는 상위 클래스에서 물려받은 관계. 물려받은 속성은 박스 안 "…에서 상속" 구역에 회색으로 표시 |
| 박스 안 "하위 클래스 N개" | `--collapse`로 접힌 말단 하위 클래스 |

## Reference

### CLI 옵션

| 옵션 | 설명 |
|---|---|
| `-o PATH` | 출력 파일. 확장자로 형식 결정(`.png`, `.svg`, `.puml`) |
| `--focus CLASS`, `--depth N` | CLASS에서 N홉(기본 1, 상속과 관계 모두) 안의 클래스만. 여러 번 지정 가능 |
| `--subtree CLASS` | CLASS와 그 하위 클래스 전체 |
| `--exclude PATTERN` | IRI에 PATTERN이 들어가거나 이름·라벨이 같은 클래스 제외 |
| `--collapse N` | 속성·관계 없는 말단 자식이 N개를 넘으면 부모 박스 안에 이름만 나열 |
| `--names both\|label\|name` | 표시 이름(기본 both) |
| `--notes none\|focus\|all` | 설명 노트를 붙일 범위(기본 focus) |
| `--no-attributes` | 속성 줄 숨김 |
| `--no-inherited` | 상위 클래스에서 물려받은 관계·속성 숨김 |
| `--individuals` | 개체 표시 |
| `--color-by source` | `dcterms:source`별 배경색 |
| `--direction tb\|lr` | 위→아래(기본) 또는 왼쪽→오른쪽 |
| `--no-legend` | 기호 범례 숨김 |
| `--title TEXT`, `--font FONT` | 제목, 폰트(Linux에서 한글이 깨지면 `"Noto Sans CJK KR"`) |
| `--lang ko` | 라벨·설명 우선 언어 |
| `--namespace PREFIX=NAME` | PREFIX로 시작하는 IRI를 표준 NAME으로 표시 |
| `--no-standards` | 표준 온톨로지 표시 끔 |
| `--overlay FILE` | 보고용 메모·색·숨김 (아래) |
| `--compare OLD_TTL` | 이전 버전과 비교 |
| `--keep-puml` | 이미지 옆에 `.puml` 남김 |
| `--plantuml-jar PATH` | `PLANTUML_JAR` 대신 직접 지정 |

### `views.yaml` 최상위 키

| 키 | 설명 |
|---|---|
| `ontology` | TTL 경로 (필수) |
| `compare` | 비교할 이전 TTL |
| `lang` | 라벨 우선 언어(기본 ko) |
| `namespaces` | `{PREFIX: NAME}` 형태로 표준 온톨로지 추가 등록 |
| `output_dir`, `format` | 보고용 뷰의 출력 폴더(기본 `out`)와 형식(기본 png) |
| `defaults` | 모든 뷰와 `per_class`에 공통 적용할 뷰 키 |
| `views` | 보고용 뷰 목록. 각 항목에 `name`이 필수 |
| `per_class` | 클래스별 그림. `classes`, `output_dir`, `format`과 뷰 키(`focus`, `subtree`, `title` 제외) |

### 보고용 메모: overlay

TTL에 넣기 애매한 보고용 메모·강조·숨김은 별도 YAML로 덧붙인다. 키는 로컬 이름, 라벨, IRI 모두 된다.

```yaml
title: 차량 중심 뷰 (v1.3)
notes:
  Truck: 이번 분기 속성 3개 추가
hide: [Thing]
colors:
  Truck: "#ffd6d6"
```

### 표준 온톨로지 판별

네임스페이스로 판별한다. 기본으로 아는 표준은 BFO, RO, IAO, OBI, IOF, CCO, schema.org, PROV-O, SOSA/SSN, OWL-Time, SKOS, DCMI Terms, FOAF, QUDT, gist다(`src/on2uml/standards.py`). 사내 표준은 `--namespace`나 `namespaces:`로 추가하고, 여러 prefix에 걸리면 가장 긴 prefix를 따른다.

### 아직 그리지 않는 것

`owl:complementOf`, `owl:oneOf`, 중첩된 Restriction은 경고만 출력한다. `owl:disjointWith`, `rdfs:subPropertyOf`, property chain은 무시한다. 상속받은 관계를 다시 그리는 것은 `--focus` 클래스에만 적용된다.

### 주의

- `.gitignore`는 `examples/`와 `tests/data/` 밖의 `.ttl`과 렌더링 결과를 제외한다. 실제 온톨로지와 그 그림은 이 저장소에 커밋하지 말고, TTL을 관리하는 저장소에 둔다.
- PlantUML 본 배포판은 GPL이다. on2uml은 PlantUML을 별도 프로세스로 호출만 하고 저장소에 포함하지 않는다.

### 개발

```bash
uv run --group dev pytest
```

## License

[MIT](LICENSE)
