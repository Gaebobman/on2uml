# on2uml

[English](README.md) | **한국어**

OWL 온톨로지(Turtle `.ttl`)를 UML 클래스 다이어그램 이미지로 바꾼다. 그림은 TTL에서 매번 다시 생성한다. TTL을 고친 뒤 같은 명령을 다시 실행하면 그림도 최신이 된다. 렌더링은 로컬에서 하고, 온톨로지를 외부로 보내지 않는다.

![예제](docs/example.png)

## 설치

uv, Java 11 이상, Graphviz, PlantUML jar가 필요하다.

```bash
git clone https://github.com/Gaebobman/on2uml.git && cd on2uml
uv sync
brew install graphviz                       # Ubuntu: sudo apt install graphviz
mkdir -p ~/.local/share/plantuml
curl -L -o ~/.local/share/plantuml/plantuml.jar \
  https://github.com/plantuml/plantuml/releases/download/v1.2024.7/plantuml-1.2024.7.jar
echo 'export PLANTUML_JAR=~/.local/share/plantuml/plantuml.jar' >> ~/.zshrc && source ~/.zshrc
```

확인: `java -jar "$PLANTUML_JAR" -testdot` → `Installation seems OK`가 나오면 Java, Graphviz, PlantUML이 모두 준비된 것이다.

## 그림 한 장

```bash
uv run on2uml examples/vehicle.ttl -o out/truck.png --focus Truck
```

확인: `out/truck.png  (4 classes)`가 출력되고 `out/truck.png` 파일이 생긴다.

`--focus`에는 로컬 이름(`Truck`), 라벨(`트럭`), IRI 중 하나를 쓴다. 클래스가 많으면 한 장에 다 그렸을 때 너무 넓어진다. 이때는 한 클래스 주변만 그리거나(`--focus`, `--depth`), 말단 클래스를 부모 박스 안에 접는다(`--collapse 3`). 전체 옵션은 `uv run on2uml --help`에 있다.

## 정기 작업: `views.yaml`

뽑을 그림 목록을 `views.yaml` 하나에 적고 한 번에 생성한다.

```bash
cp examples/views.yaml <온톨로지-폴더>/views.yaml
uv run on2uml --config <온톨로지-폴더>/views.yaml
```

`<온톨로지-폴더>`는 TTL 파일이 있는 폴더다. 복사한 파일에서 `ontology:`를 TTL 파일 이름으로, `views`의 클래스 이름(`Truck` 등)을 내 클래스로 바꾼다. 쓸 수 있는 키는 그 파일의 주석에 있고, 뷰 하나만 생성할 때는 `--only <뷰 이름>`을 붙인다.

확인: 뷰마다 `[<뷰 이름>] <온톨로지-폴더>/out/<뷰 이름>.png  (N classes)`가 출력된다.

`per_class`는 클래스마다 그림을 한 장씩 만든다. 다시 실행하면 바뀐 그림만 렌더링하고 변경 내역을 출력한다. 아래는 예제에서 `Motorcycle`을 지우고 `Bus`에 속성을 추가한 뒤 실행한 결과다.

```text
[per_class] out/classes  (added 0, changed 2, removed 1, unchanged 5)
  changed: Bus, Vehicle
  removed: Motorcycle
```

변경은 그림 단위로 센다. 상위 클래스를 고치면 그 내용을 물려받아 보여 주는 하위 클래스 그림도 변경으로 잡힌다. 삭제된 클래스의 그림은 지워진다. 출력 폴더의 `index.md`에 전체 목록과 마지막 변경 목록이 있다. `views.yaml`과 출력 폴더를 TTL 저장소에 커밋하면 `.puml` 파일의 `git diff`가 그림 변경 이력이 된다.

이전 버전과의 차이는 `--compare <이전 TTL>`로 색칠한다. `views.yaml`에서는 `compare:` 키를 쓴다. `<이전 TTL>`은 Git에서 꺼낸다(예: `git show <태그>:ontology.ttl > old.ttl`).

보고용 메모, 강조색, 숨길 클래스는 overlay YAML로 덧붙인다(`--overlay`). TTL은 바뀌지 않는다. 형식은 [`overlay.py`](src/on2uml/overlay.py) 상단에 있다.

개체(named individual)는 `--individuals`(그린 클래스 전부) 또는 `--individuals-focus`(`--focus` 클래스만)로 그린다. `--individuals-hide CLASS`는 그 클래스(하위 클래스 제외)의 개체를 뺀다. 예: 수백 개의 `skos:Concept` 값. focus 클래스라도 뺀다. `views.yaml`에서는 `individuals: true | focus`, `individuals_hide: [Concept]`로 쓴다.

## 그림 읽기

그림마다 범례가 붙는다. 범례에는 그 그림에 쓰인 기호만 나온다.

| 그림 | TTL |
|---|---|
| 자식 ──▷ 부모 | `rdfs:subClassOf` |
| A ──> B : 이름 | `owl:ObjectProperty` (domain → range) |
| 화살표 끝 `1..*`, `«only»` | `owl:Restriction` (some, min/max/exact, only) |
| 박스 안 `이름 : 타입` | `owl:DatatypeProperty` |
| 보라 점선, 박스 안 "…에서 상속" | 그림 밖 상위 클래스에서 물려받은 관계·속성 |
| `«BFO»`, `«IOF»`, 회색 박스 | 표준 온톨로지 클래스 (네임스페이스로 판별) |

그리지 않는 것: `owl:complementOf`, `owl:oneOf`, 중첩된 Restriction은 경고만 출력한다. `owl:disjointWith`, `rdfs:subPropertyOf`는 무시한다.

## 온톨로지 데이터 관리

`.gitignore`는 `examples/`와 `tests/data/` 밖의 온톨로지 파일, `views.yaml`, 렌더링 결과를 제외한다. 실제 온톨로지와 그 그림은 온톨로지 저장소에 둔다.

## 개발

```bash
uv run --group dev pytest
```

## License

[MIT](LICENSE). PlantUML(GPL)은 별도 프로세스로 호출하며, 이 저장소에 포함하지 않는다.
