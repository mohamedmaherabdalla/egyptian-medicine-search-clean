# شرح عرض Algorithm 6

ده الشرح النصي للـ44 جزء من عرض Algorithm 6. ملف العرض نفسه غير منشور على GitHub؛ النص هنا هو النسخة الموثقة والمراجعة للاجتماع. كل جزء يبدأ من السؤال اللي بيحاول يجاوبه، ثم يوضح الـinput، اللي بيحصل، مثال، وأهم استنتاج.

---

## Slide 1: Algorithm 6

### الشرح

**الفكرة:** Algorithm 6 هي محرك بحث عن أسماء الأدوية التجارية، وليست OCR model وليست نظام تشخيص.

**الـinput:** نص فيه اسم دواء، سواء كتبه المستخدم أو خرج من OCR. مثلا:

```text
MYMLAX
```

الاسم الصحيح في الـcatalog هو `MYOLAX`، لكن الـalgorithm لا تعرف ذلك مسبقا.

**ما يحدث:** تبحث داخل قاعدة الأدوية المصرية، تجمع الأسماء المحتملة، ثم ترتبها حسب قوة الأدلة. البحث يتم على مستوى medicine family، لذلك العبوات المختلفة لنفس الاسم لا تحتل ranks منفصلة.

**الـoutput:** قائمة مرتبة بحد أقصى 20 family. في المثال تظهر `MYOLAX` في rank 1.

**نقطة الأمان:** rank 1 معناها أقوى مرشح، وليس تأكيدا طبيا. النظام يعرض `ambiguous` عندما يحتاج المستخدم للمقارنة، ويرجع `no_match` عندما لا توجد حروف كافية.

---

## Slide 2: What Algorithm 6 Receives and Returns

### الشرح

**المدخل له شكلان:**

1. نص عادي، مثل `MYMLAX`.
2. نص ومعه مكان جزء غير مقروء، مثل `RIV` مع معلومة أن هناك حروفا بعده.

الفرق مهم. `RIV` وحدها قد تشير إلى `RIVO`. أما `RIV` مع `unreadable after` فمعناها أن الاسم أطول، ولذلك `RIVOTRIL` تصبح اختيارا منطقيا.

**قاعدة البيانات:** فيها `25,066` product row، لكن هذه الصفوف تمثل `17,476` family فقط. عبوات وتركيزات الاسم نفسه تبقى داخل family واحدة.

**الناتج:** بحد أقصى 20 family، وكل واحدة يمكن أن تعرض الاسم والـvariants والـingredients وأسباب ظهورها. الرد نفسه يكون:

```text
ambiguous  = توجد اختيارات، ويجب التأكد
no_match   = لا يوجد دليل كاف
```

**مثال القياس:** `MYMLAX` تدخل، و`MYOLAX` تظهر rank 1. بعد انتهاء البحث فقط يقارن الـevaluator الناتج بالـground truth ويحسب Hit@1 وHit@20. الإجابة الصحيحة لا تدخل مرحلة البحث.

---

## Slide 3: The Entire Algorithm, Flattened

### الشرح

السلايد دي خريطة الرحلة كاملة. فكر فيها كخمس مراحل:

1. **فهم النص:** نقرأ الاسم ومكان أي جزء غير مقروء.
2. **توحيد الكتابة:** نحول النص إلى شكل ثابت، من غير تصحيحه.
3. **جمع المرشحين:** نبحث بالاسم الكامل، وأجزاء الحروف، والنطق، والحروف الناقصة، وبنية الـfamily.
4. **الترتيب:** كل family تأخذ score من عدة أدلة، ثم تطبق تصحيحات ترتيب محدودة.
5. **الـconsensus والأمان:** طرق بحث مستقلة تحاول إنقاذ target مفقودة، ثم النظام يعرض الاختيارات أو يرجع no match.

**مثال `MYMLAX`:** الاسم يتوحد إلى `MYMLAX`. البحث يجد `MYOLAX` بسبب edit واحدة وأجزاء حروف مشتركة، ثم يضعها rank 1.

**مثال `TEFA`:** الجزء الأساسي لم يجد `TELFAST` داخل top 20. ثلاث طرق مستقلة وجدتها، فدخلت rank 20 فقط. أول 19 نتيجة لم تتغير.

**الرقم المهم:** الجزء الأساسي استغرق في المتوسط `28.54 ms`. النظام الكامل بالـconsensus استغرق `48.50 ms` لكل query على مجموعة الـOCR.

---

## Slide 4: Offline Catalog Preparation

### الشرح

قبل أن تدخل أي query، نجهز دليل بحث مرة واحدة عند تشغيل البرنامج.

1. **نجمع المنتجات في families.** قاعدة البيانات فيها `25,066` product row. العبوات المختلفة للاسم نفسه تتجمع، فيتبقى `17,476` family.

2. **نخزن أكثر من شكل للاسم.** مثلا:

```text
CLEX-A NE
CLEX A NE
CLEXANE
```

الثلاثة يصلون إلى compact key واحدة هي `CLEXANE`. نحن لا ننشئ ثلاثة أدوية، بل ثلاثة طرق للوصول إلى نفس الـfamily.

3. **نبني فهارس سريعة.** الـindex مثل دليل الكتاب. المفتاح `RIV` يشير مباشرة إلى families تبدأ بـ`RIV`. والنهاية `TRIL` تصل إلى الأسماء التي تنتهي بها باستخدام reversed index.

4. **نخزن أجزاء الحروف.** `MYOLAX` تحتوي `MY`, `YO`, `OL`, `LA`, `AX`. لذلك `MYMLAX` ما زالت تشارك `MY`, `LA`, و`AX`.

5. **نخزن أشكال النطق والحذف.** consonant skeleton تساعد مع wrong vowels، وdeletion keys تساعد query مثل `RIO` تصل إلى `RIVO` من غير قاعدة خاصة باسم الدواء.

6. **نحفظ علاقات الـfamily.** `ABIMOL` head موثقة لـ`ABIMOL EXTRA`، لذلك يمكن عرض الـvariant الأطول عندما يقول المستخدم إن هناك حروفا بعدها.

**الخلاصة:** التحضير لا يختار الدواء. هو يبني طرقا سريعة لجلب المرشحين. زمن `48.50 ms` هو زمن query بعد هذا التحضير، وليس زمن startup.

---

## Slide 5: Parse the Query and the Unreadable Position

### الشرح

**المشكلة:** نفس الحروف يمكن أن تعني أشياء مختلفة حسب مكان الجزء غير المقروء.

**الحالات الأربع:**

```text
none    كل النص الظاهر هو المكتوب
after   توجد حروف غير مقروءة بعد النص
before  توجد حروف غير مقروءة قبل النص
middle  البداية والنهاية ظاهرتان والوسط غير مقروء
```

**أمثلة:**

```text
ABIMOL + none   -> ABIMOL نفسها مرشح قوي
ABIMOL + after  -> ابحث عن اسم أطول يبدأ بـ ABIMOL، مثل ABIMOL EXTRA
MOL + before    -> ابحث عن اسم أطول ينتهي بـ MOL
AB + OL         -> ابحث عن اسم يبدأ بـ AB وينتهي بـ OL
```

الـparser لا يبحث عن الأدوية. هو يخرج النص والـmode والجزء الظاهر في البداية أو النهاية. المراحل التالية تستخدم هذه المعلومة لتمنع wildcard مفتوحة تجلب أسماء غير مرتبطة.

**الخلاصة:** معلومة مكان الحروف المفقودة قد تكون أقوى من تشابه النص نفسه.

---

## Slide 6: Normalization, One Transformation at a Time

### الشرح

**الفكرة:** normalization توحد طريقة الكتابة، لكنها لا تصحح اسم الدواء.

نأخذ:

```text
Clex-A NE 40 mg tab
```

ثم نحولها خطوة بخطوة:

```text
Uppercase:  CLEX-A NE 40 MG TAB
Normalized: CLEX A NE 40 MG TAB
Compact:    CLEXANE40MGTAB
```

الـnormalized form تحتفظ بالمسافات، لذلك تفيد الطرق التي تتعامل مع الكلمات. الـcompact form تحذف المسافات والعلامات، لذلك تفيد edit distance وأجزاء الحروف.

مثال أبسط:

```text
mymlax -> normalized MYMLAX -> compact MYMLAX
```

لم تتحول إلى `MYOLAX`. التصحيح يبدأ في retrieval، وليس normalization.

**الـoutput:** نسختان ثابتتان من نفس input، وكل طريقة بحث تستخدم النسخة المناسبة لها.

---

## Slide 7: Context Cleanup, Token by Token

### الشرح

**المشكلة:** النص قد يحتوي اسم الدواء ومعه dose وunit وform. هذه الكلمات تشوش مقارنة الاسم.

مثال:

```text
CLEX A NE 40 MG TAB
```

نراجع كل token:

```text
CLEX A NE  -> نحتفظ بها لأنها قد تكون الاسم
40         -> رقم جرعة
MG         -> وحدة
TAB        -> شكل دوائي
```

النسخة المنظفة تصبح:

```text
CLEX A NE -> compact CLEXANE
```

النظام يبحث بالنسخة الأصلية والمنظفة معا. السبب أن كلمة تبدو كـcontext قد تكون أحيانا جزءا من brand، فلا نريد أن نحذف دليلا صحيحا نهائيا.

**مثال آخر:** `AUGMENTIN 1 GM TAB` تنتج clean query هي `AUGMENTIN`. أما `MYMLAX` فلا تحتوي context، لذلك لا تحتاج pass ثانية.

**الخلاصة:** cleanup تفصل الاسم عن معلومات العبوة، لكنها لا تلغي البحث بالنص الأصلي.

---

## Slide 8: Full-Name Typo Retrieval

### الشرح

**الفكرة:** أول محاولة بحث تقارن الـquery كاملة بأسماء الـcatalog.

Input:

```text
MYMLAX
```

أول خمس نتائج كانت:

```text
1. MYOLAX
2. MAALOX
3. MINALAX
4. MYORELAX
5. MICLOX
```

`MYOLAX` وصلت rank 1 لأن الطول متساو، وخمسة من ستة positions متطابقة، والفرق حرف واحد فقط.

مع query فيها context، نبحث بالنسختين. مثلا النص الكامل `CLEX-A NE 40 MG TAB` قد يكون noisy، لكن النسخة المنظفة `CLEX A NE` تصل إلى `CLEXANE`.

**حدود هذه المرحلة:** تعمل جيدا عندما معظم الاسم ظاهر. قد تفشل مع fragment قصيرة أو عدة أخطاء متزامنة. لذلك نتائجها مرشحين أوليين، وليست القائمة النهائية.

---

## Slide 9: Indexed Family Rescue, Lookup by Lookup

### الشرح

**المشكلة:** البحث بالاسم الكامل قد يفقد family صحيحة رغم وجود أجزاء مفيدة من الاسم.

Family rescue تسأل عدة فهارس جاهزة:

```text
Exact compact: CLEXANE -> CLEXANE
Prefix:        RIV -> RIVO, RIVOTRIL, ...
Suffix:        MOL -> families تنتهي بـ MOL
Character:     MYMLAX تشارك MY وLA وAX مع MYOLAX
Skeleton:      KITORILIC تقترب من KETOROLAC
Phonetic:      FARMA تقترب من PHARMA
Deletion:      RIO تصل إلى RIVO
Family head:   ABIMOL تصل إلى ABIMOL EXTRA عند وجود unreadable after
```

كل lookup ترجع family IDs ومعها سبب الدخول. بعدها نأخذ union، أي نجمع كل الـIDs من غير تكرار.

**المهم:** ظهور family في index لا يجعلها صحيحة. هو فقط يسمح لها بالدخول إلى candidate pool، ثم مرحلة scoring تقارنها ببقية الأسماء.

---

## Slide 10: Bound the Candidate Pool Before Scoring

### الشرح

**المشكلة:** query قصيرة مثل `LANS` قد تطابق آلاف الأسماء. حساب كل features لكل الأسماء سيكون بطيئا ومليئا بالضوضاء.

لذلك نعمل prefilter:

1. نراجع أول حرف أو confusion محتملة.
2. نرفض فرق الطول المبالغ فيه، إلا إذا كان هناك fragment evidence قوية.
3. نطلب دليلا إضافيا مثل n-gram مشتركة أو skeleton أو phonetic key أو family head.
4. لو العدد ما زال كبيرا، نضع cap ثابت عند `2,200` family قبل scoring.

الـ`2,200` ليست عدد النتائج التي يراها المستخدم. هي أقصى عدد يدخل الحساب الغالي. الناتج النهائي ما زال بحد أقصى 20.

**لماذا هذا ليس تحسين سرعة فقط؟** عندما أزلنا compatible-length scan، OCR Hit@20 هبطت من `73.28%` إلى `71.77%`. إذن طريقة اختيار الـpool تؤثر في وجود الإجابة الصحيحة أصلا.

---

## Slide 11: Generate General OCR and Typo Variants

### الشرح

**الفكرة:** نجرب أخطاء عامة يمكن أن تحدث لأي اسم، وليس mapping خاصا بحالات الـtest.

أمثلة للـrules:

```text
Keyboard:      حذف، تكرار، حرف مجاور، أو swap
Visual OCR:    0/O, 1/I/L, 2/Z, 5/S, 8/B
Ligature:      RN/M, CL/D, IV/N
Phonetic:      PH/F, CK/K, X/KS, GH/G, SH/CH
Vowels:        تغيير أو حذف vowels مع حفظ consonants
```

أمثلة:

```text
C0LCHICINE -> استبدال 0 بـ O -> COLCHICINE
TAVANCI    -> swap بين I وC -> TAVANIC
COUFSED    -> phonetic variants -> COUGHSED candidate
```

يمكن تركيب خطوتين أو ثلاث لحالة متعددة الأخطاء، لكن عدد الخطوات والنواتج محدود. كل تحويل إضافي يأخذ penalty.

**الخلاصة:** الـgenerated form لا تصبح الإجابة. هي طريقة أخرى لجلب family من الـcatalog، ويجب أن تنجح بعد ذلك في scoring والـreranking.

---

## Slide 12: Family Score, Exact Formula and Full Calculation

### الشرح

**السؤال:** بعد جمع المرشحين، كيف نرتبهم؟

كل query وfamily ينتج عنهما 12 feature. كل feature تقيس نوعا مختلفا من الاتفاق، ثم نضربها في وزن ونجمعها.

مثال `MYMLAX` مع `MYOLAX`:

```text
Exact match                 = 0
Raw edit similarity         = 0.833
Weighted edit similarity    = 0.833
Prefix coverage             = 0.333
Suffix coverage             = 0.500
Bigram overlap              = 0.429
Trigram overlap             = 0.143
Consonant skeleton          = 1
Phonetic key                = 1
Positional agreement        = 0.833
Length coverage             = 1
```

بعد الأوزان، الـbase score تقارب `1.75`. اتفاق أول حرف والطول يضيف bonuses، فتصل النتيجة إلى نحو `2.05`.

**مهم:** `2.05` ليست probability ولا تعني ثقة 205%. هي قيمة ترتيب داخلية. الـadmission threshold العادية هي `.62`، أي إن `MYOLAX` تدخل القائمة بقوة ثم تقارن ببقية المرشحين.

---

## Slide 13: Edit and Boundary Evidence

### الشرح

السلايد تشرح أول مجموعة من الـfeatures:

1. **Exact compact:** هل الاسمان متطابقان بعد حذف المسافات والعلامات؟
2. **Levenshtein:** أقل عدد edits لتحويل query إلى candidate.
3. **Weighted edit:** نفس الفكرة، لكن أخطاء OCR الشائعة تكلف أقل.
4. **Prefix coverage:** كم من بداية الاسم ظاهر؟
5. **Suffix coverage:** كم من نهاية الاسم ظاهر؟
6. **Bigrams وtrigrams:** ما أجزاء الحروف المحلية المشتركة؟

مثال edit distance:

```text
MYMLAX -> MYOLAX
```

تحتاج substitution واحدة من طول 6، لذلك similarity هي:

```text
1 - 1/6 = 0.833
```

مثال prefix:

```text
RIV داخل RIVOTRIL = 3/8 = 0.375
```

ومثال bigrams، `MYMLAX` و`MYOLAX` يشتركان في `MY`, `LA`, و`AX`.

**الخلاصة:** edit تقيس حجم الخطأ، boundaries تحدد مكان الجزء الظاهر، وn-grams تحفظ القطع السليمة حول الحرف الخطأ.

---

## Slide 14: Shape and Sequence Evidence

### الشرح

المجموعة الثانية تنظر إلى شكل الاسم وترتيب الحروف:

1. **Consonant skeleton:** تقلل أثر wrong vowels. `KITORILIC` و`KETOROLAC` يقتربان من `KTRLK`.
2. **Phonetic key:** تجمع كتابات لنطق قريب، مثل `PHARMA` و`FARMA`.
3. **Subsequence:** هل حروف query موجودة بنفس الترتيب داخل candidate؟
4. **Positional agreement:** كم حرفا موجود في نفس المكان؟
5. **Visible-length coverage:** كم من الاسم الكامل ظاهر؟

مثال:

```text
MYMLAX / MYOLAX
```

خمسة positions من ستة متطابقة، لذلك positional agreement تساوي `.833`، والطول متساو، لذلك length coverage تساوي `1`.

أما:

```text
RIV / RIVOTRIL
```

الحروف مرتبة صح، لكن الظاهر 3 حروف فقط من 8. لذلك candidate مفيدة للعرض، لكنها لا تستحق ثقة عالية.

---

## Slide 15: Bonuses, Penalties, and Admission

### الشرح

بعد جمع الـfeatures، توجد تعديلات صغيرة:

**Bonuses** عندما يتفق أكثر من دليل:

```text
نفس أول حرف                         +0.12
أول حرف داخل confusion group        +0.06
طول قريب مع weighted edit قوية      +0.18
Prefix قوية مع edit evidence         +0.08
Edit قوية مع positional agreement    +0.22
```

**Penalties** عندما يكون النص ناقصا أو الأدلة ضعيفة:

```text
Fragment قصيرة من اسم طويل          -0.18 أو أكثر
حرف واحد فقط                         -0.22
Edit والصوت والشكل جميعها ضعيفة      -0.20
Prefix وgrams وedit جميعها ضعيفة     -0.10
```

بعد ذلك يجب أن تصل candidate عادة إلى `.62` كي تدخل القائمة. يوجد threshold أقل `.58` لكنه يحتاج شروطا إضافية في أول حرف والمواقع والطول.

**الخلاصة:** threshold تقول إن الاسم يستحق العرض، ولا تقول إنه صحيح طبيا.

---

## Slide 16: Score Family Heads Without Collapsing Unrelated Drugs

### الشرح

**المشكلة:** أحيانا المستخدم يرى الجزء الأساسي من brand، بينما الـvariant غير واضحة.

مثال:

```text
ABIMOL       = family موجودة
ABIMOL EXTRA = variant أطول
```

الـcatalog تسجل أن `ABIMOL` head موثقة لـ`ABIMOL EXTRA`. لذلك إذا قال المستخدم إن هناك حروفا بعد `ABIMOL`، يمكن تقييم الـhead نفسها بدلا من معاقبة الاسم الطويل على كلمة `EXTRA` المفقودة.

مثال آخر `LANS` قد يوصل إلى `LANTUS` من head evidence، لكن يظل الرد محتاج confirmation لأن الجزء قصير.

**الحماية المهمة:** أي اسمين يبدأان بنفس الكلمة لا يصبحان family واحدة. `ABC` قد تبدأ عدة أدوية مختلفة. الدمج يحدث فقط عندما تكون علاقة الـvariants موجودة في بيانات الـcatalog.

**الدليل التجريبي:** إزالة family-head rescue أخرجت حالات مثل `LANS -> LANTUS` من top 20.

---

## Slide 17: Merge Three Deterministic Evidence Paths

### الشرح

قبل الـconsensus توجد ثلاث قوائم:

```text
1. البحث بالنص الكامل
2. البحث بالنص بعد إزالة dose وform
3. family rescue والـvariant evidence
```

نفس family قد تظهر في القوائم الثلاث. بدلا من تكرارها، نجمعها باستخدام compact family key.

مثال `MYMLAX`:

```text
Full-name path -> MYOLAX rank 1
Rescue path    -> MYOLAX من edit وn-grams
```

النتيجة record واحدة لـ`MYOLAX`، تحتفظ بأقوى score وكل أسباب الظهور، وتأخذ bonus صغير لأن طريقين مستقلين اتفقا.

ومع `CLEX...40 MG TAB`، clean path قد تجد `CLEXANE` والrescue تجد نفس الـfamily من exact compact. بعد الدمج تظهر مرة واحدة فقط.

**الـoutput:** قائمة families فريدة، وكل family تحمل الأدلة التي جاءت من كل path.

---

## Slide 18: Deterministic Reranking Uses Bounded Corrections

### الشرح

**المشكلة:** الـscore العامة قد تضع الإجابة الصحيحة rank 2 بفارق صغير رغم وجود error pattern واضحة.

الـreranker لا تبحث من جديد. هي تسمح بحركة محددة داخل القائمة عندما يتحقق شرط واضح:

```text
Unique nearest:       candidate أقرب وحدها بوضوح
Visual exact:         0/O أو confusion بصرية تصل إلى exact key
Phonetic + position:  النطق والمواقع يتفقان
Skeleton + position:  consonants والanchors يتفقان
Family head:          head موثقة مع evidence كافية
Multi-step chain:     خطوات عامة محدودة تصل إلى exact key
```

مثال `MYOLANA -> MYOLAX`: `MYOLAX` كانت موجودة لكنها تحتاج حركة محدودة إلى rank 1.

إذا كانت المسافات متساوية أو advantage ضعيفة، الترتيب لا يتغير ويظل الرد ambiguous.

**الدليل:** عند إغلاق كل deterministic reranking، OCR Hit@1 هبطت من `50.43%` إلى `40.52%`. إذن الـreranker تصلح ترتيب candidates موجودة فعلا، وليست hardcoded answers.

---

## Slide 19: The First Five Independent Retrievers

### الشرح

بعد القائمة الأساسية، نشغل طرق بحث مستقلة. كل طريقة ترى query والـcatalog فقط، ثم ترجع top 20 الخاصة بها.

أول خمس طرق:

```text
Jaro-Winkler       تحفظ ترتيب الحروف وتعطي أهمية للبداية
Match Rating       تقارن consonant pronunciation codes
WRatio             تجمع full وpartial وtoken matching
NYSIIS             phonetic encoding مختلف
BM25+ trigrams     تعطي وزنا أكبر لقطع الحروف النادرة
```

أمثلة:

```text
TEFA       -> TELFAST rank 1 عند Jaro
ABASCOLOGY -> ABASAGLAR rank 1 عند Match Rating
LACTULOSE  -> LACTO rank 3 عند WRatio
MYOLOGY    -> MYOLAX rank 1 عند NYSIIS
LACTULOSE  -> LACTO rank 12 عند BM25+
```

الأزمنة المنفردة تراوحت تقريبا من `.07 ms` لـBM25+ إلى `3.76 ms` لـWRatio. هذه أزمنة warm standalone، وليست تكلفة Algorithm 6 كاملة.

---

## Slide 20: The Remaining Four Independent Retrievers

### الشرح

الطرق الأربع الباقية:

```text
SymSpell        deletion dictionary حتى 3 edits
Token-sort      تقارن الكلمات بعد ترتيبها
Soundex         code صوتية واسعة
Dice bigrams    نسبة أجزاء الحروف الثنائية المشتركة
```

أمثلة:

```text
OSFOCU  -> OSTOCAL rank 1 عند SymSpell
TEFA    -> TELFAST rank 2 عند token-sort
TELBACE -> TELFAST rank 1 عند Soundex
TEFA    -> TELFAST rank 15 عند Dice
```

القائمة deterministic هي source عاشرة. لذلك كل query قد تنتج عشر قوائم، كل قائمة فيها حتى 20 family.

مجموع أزمنة الطرق التسع منفردة حوالي `6.71 ms`، لكن تكلفة إضافتها داخل النظام كانت `19.96 ms`. الفرق يشمل الدمج وإعادة الحساب والترتيب وPython overhead، لذلك لا ننسبه كله إلى retriever واحدة.

---

## Slide 21: Build One Consensus Record per Family

### الشرح

عشر قوائم في 20 نتيجة تعني حتى 200 ظهور، لكن نفس family قد تظهر في عدة قوائم. نجمع كل ظهور في record واحدة.

الـrecord تحفظ:

```text
C     عدد المصادر التي أرجعت الـfamily
Ranks ترتيبها داخل كل مصدر
RRF   قيمة تجمع هذه الرتب
L/J/D Levenshtein وJaro وDice مع query
```

RRF تضيف لكل ظهور:

```text
1 / (60 + rank)
```

لذلك rank 1 تضيف `.01639` وrank 14 تضيف `.01351`. الثابت 60 يجعل عدد المصادر أهم من فرق بسيط في rank.

مثال `MYMLAX -> MYOLAX`: ظهرت `MYOLAX` في 9 من 10 sources، وRRF كانت `.1439`، وLevenshtein `.8333`، وJaro `.9111`، وDice `.600`.

**الخلاصة:** الـrecord تلخص كم طريقة وافقت، وأين رتبت الاسم، ومدى قرب النص منه.

---

## Slide 22: Consensus Ordering

### الشرح

نرتب consensus records بهذا الترتيب:

```text
1. عدد المصادر C
2. مجموع RRF
3. Levenshtein similarity
4. Jaro-Winkler similarity
5. اسم الـfamily لكسر أي تعادل
```

مثال:

```text
MYOLAX    ظهرت في 9 sources، RRF = .143876
MYORELAX  ظهرت في 7 sources، RRF = .109917
```

لذلك `MYOLAX` تتقدم بسبب اتفاق مصادر أكثر.

لكن هذا الترتيب لا يملك صلاحية تغيير rank 1. جربنا consensus واسعة لأول نتيجة، فكسبت 27 synthetic case وخسرت 138. السبب أن طرقا متشابهة قد تتفق على إجابة خاطئة.

**الخلاصة:** consensus الحالية مخصصة لإنقاذ missing candidate في نهاية top 20، وليست بديلا عن ترتيب الـcore.

---

## Slide 23: The Only Enabled Consensus Rewrite

### الشرح

النظام ينسخ أول 20 نتيجة من الـcore كما هي. بعد ذلك يسمح بتغيير واحد فقط:

```text
Family واحدة خارج القائمة يمكنها دخول rank 20
```

لكي تدخل يجب أن تحقق:

```text
عدد المصادر المستقلة >= 3
Levenshtein similarity >= .55
Jaro-Winkler similarity >= .85
```

أمثلة:

```text
TEFA -> TELFAST
3 sources، Levenshtein .571، Jaro .886 -> تدخل rank 20

OSCAR -> OSTOCAL
مصدران فقط وJaro .832 -> ترفض

RIV -> RIVOTRIL
مصدران وLevenshtein .375 -> ترفض
```

**النتيجة المقاسة:** على 464 OCR pair، الـgate أضافت حالتين إلى Hit@20 بلا أي paired loss. Hit@20 ارتفعت من `72.84%` إلى `73.28%`، وHit@1 لم تتغير.

---

## Slide 24: Worked Example, TEFA to TELFAST

### الشرح

نمشي بالحالة خطوة بخطوة:

```text
Input:    TEFA
Expected: TELFAST
```

1. normalization لا تغير النص.
2. القائمة deterministic تضع `TERA` rank 1، ولا تضع `TELFAST` داخل top 20.
3. Jaro ترجع `TELFAST` rank 1.
4. token-sort ترجعها rank 2.
5. Dice ترجعها rank 15.
6. عدد المصادر يصبح 3.
7. Levenshtein تساوي `.571` وJaro `.886`.
8. الشروط الثلاثة تنجح، فتدخل `TELFAST` rank 20.

**الناتج:** `TERA` تظل rank 1، و`TELFAST` تصبح rank 20، والرد يظل `ambiguous`.

**معنى النجاح:** الحالة تحولت من Hit@20 = 0 إلى Hit@20 = 1. النظام لم يدع أن `TELFAST` مؤكدة، لكنه منع اختفاءها من قائمة المقارنة.

---

## Slide 25: Worked Example, MYMLAX to MYOLAX

### الشرح

```text
Input:    MYMLAX
Expected: MYOLAX
```

1. الاسمان طولهما 6.
2. الفرق substitution واحدة، لذلك Levenshtein = `5/6 = .833`.
3. خمس positions من ستة متطابقة.
4. full-name search تضع `MYOLAX` rank 1.
5. family rescue تدعمها من edit وn-grams وphonetic evidence.
6. score النهائية تقارب `2.05`.
7. بعد تشغيل باقي الطرق، تظهر `MYOLAX` في 9 من 10 sources.

الـconsensus لا تحتاج تغيير القائمة لأن target موجودة بالفعل في rank 1.

**الناتج:** `MYOLAX` rank 1، لكن `status=ambiguous` و`needs_clarification=true`.

**مهم:** probability تظهر `0.0` لأن الـcalibrator غير مفعلة، وليس لأن احتمال الاسم صفر.

---

## Slide 26: Final Safety State and the Disabled Calibrator

### الشرح

بعد الترتيب توجد حالتان نشطتان:

```text
ambiguous = توجد candidates ويجب التأكد
no_match  = لا توجد candidate بدليل كاف
```

كل candidate حاليا تظل `needs_clarification=true`. Input ضعيفة مثل `H` لا تتحول إلى اسم دواء بالتخمين.

يوجد في الكود calibrator اختياري. هي logistic regression يمكنها استخدام source count وRRF وsimilarities والفروق بين أول نتيجتين لإنتاج احتمال أن top 1 صحيحة.

لكن الـpolicy الحالية لا تحتوي إعداد `abstention`، لذلك calibrator مقفولة وتعيد:

```text
probability = 0.0
likely_match = false
```

الصفر هنا يعني feature disabled، وليس confidence حقيقية.

**الخلاصة:** النظام الحالي يعرض احتمالات تحتاج confirmation أو يرجع no match. لا يتخذ dispensing decision ولا يقدم medical certainty.

---

## Slide 27: How Every Score Was Produced

### الشرح

**وحدة التقييم:** case واحدة هي query مع expected family.

```text
MYMLAX -> MYOLAX
```

إذا ظهرت target rank 1، تنجح Hit@1. وإذا ظهرت في أي rank من 1 إلى 20، تنجح Hit@20.

مجموعة OCR الأساسية فيها `464` fair unique pair:

```text
Unique = كل query-target pair تأخذ vote واحدة حتى لو تكررت من عدة OCR models
Fair   = نستبعد 17 حالة كتبت اسم دواء حقيقي مختلف عن الـtarget من single-answer accuracy
```

مثال collision: OCR output نفسها اسم دواء موجود، بينما label تقول دواء آخر. من غير مراجعة الصورة، لا يصح اعتبار اختيار الاسم المكتوب failure عادية.

المجموعة synthetic clean core فيها `66,257` pair بعد فلترة exact-name collisions.

كل الطرق أعيد تشغيلها محليا على نفس الحالات. الـlatency هي warm single-process query time، ولا تشمل network أوUI أوstartup.

---

## Slide 28: Algorithms 1 to 6 on the Same Cases

### الشرح

السلايد تقارن تطور المشروع على نفس الـ464 OCR pairs:

```text
A1  Hit@1 23.71%  Hit@20 38.15%   1.28 ms
A2  Hit@1 25.86%  Hit@20 51.29%   4.75 ms
A3  Hit@1 25.65%  Hit@20 53.02%   rank fusion
A4  Hit@1 47.63%  Hit@20 71.12%  14.89 ms
A5  Hit@1 50.43%  Hit@20 72.84%  28.54 ms
A6  Hit@1 50.43%  Hit@20 73.28%  48.50 ms
```

**ما الذي غير النتائج؟**

```text
A2 أضافت lexical typo retrieval أقوى.
A3 دمجت A1 وA2.
A4 أضافت family rescue، وكانت أكبر قفزة.
A5 أضافت scoring وvariants وbounded reranking أوسع.
A6 أضافت consensus لإنقاذ rank 20 فقط.
```

على synthetic، A6 وصلت `98.19%` Hit@1 و`99.9985%` Hit@20، وهي نفس A5.

**الخلاصة:** A6 أضافت حالتي OCR Hit@20 بلا losses، مقابل `19.96 ms` زيادة عن A5.

---

## Slide 29: External Lexical Baselines

### الشرح

الـbaseline هي طريقة معروفة أبسط نقارن بها النظام على نفس الحالات.

أهم النتائج على OCR:

```text
SymSpell             Hit@1 38.58%  Hit@20 55.82%
Damerau-Levenshtein  Hit@1 34.27%  Hit@20 59.27%
Jaro-Winkler         Hit@1 32.11%  Hit@20 67.46%
BM25+ trigrams                     Hit@20 47.41%
WRatio               Hit@1 11.21%  Hit@20 56.25%
Exact/prefix         Hit@1  2.59%  Hit@20  3.02%
Algorithm 6          Hit@1 50.43%  Hit@20 73.28%
```

Jaro هي أقوى external baseline في Hit@20 لأنها تحافظ على ترتيب الحروف وبداية الاسم.

Exact/prefix المنخفضة تثبت أن المجموعة ليست أسماء نظيفة. معظم الحالات تحتاج معالجة أخطاء حقيقية.

**الاستنتاج:** A6 تتفوق على Jaro في Hit@20 بنحو `5.82` percentage points لأنها تجمع أدلة الحروف وبنية الـfamily واتفاق عدة طرق، وليس لأنها تعتمد على similarity واحدة.

---

## Slide 30: Biomedical, Hybrid, and Phonetic Baselines

### الشرح

السلايد تسأل: هل semantic model أوphonetic code وحدها تكفي؟

النتائج:

```text
BioSyn-style hybrid      Hit@1 20.47%  Hit@20 53.02%
xMEN-style dense+sparse  Hit@1 16.81%  Hit@20 52.37%
SapBERT dense HNSW       Hit@1 11.42%  Hit@20 38.58%
Egyptian phonetic        Hit@1  6.90%  Hit@20 23.28%
```

SapBERT ممتازة في ربط medical concepts، لكن input مثل `MYMLAX` ليست جملة لها معنى. هي proper name مشوهة، لذلك الحروف أهم من semantics.

الـphonetic code وحدها واسعة جدا. أسماء كثيرة قد تحصل على نفس code، فتجلب مرشحين لكن لا ترتبهم بأمان.

**الخلاصة:** character-level retrieval يجب أن تبقى الأساس. الـsemantic والphonetic channels تصلح كأصوات إضافية داخل نظام أكبر، لا كقرار منفرد.

---

## Slide 31: External Method Provenance

### الشرح

السلايد لا تعرض accuracy جديدة. هي توضح مصدر كل method حتى يمكن مراجعة التجربة.

```text
RapidFuzz   -> Levenshtein, Damerau, WRatio
Jellyfish   -> Jaro-Winkler وphonetic encoders
SymSpell    -> مشروع Wolf Garbe
rank_bm25   -> BM25
BioSyn, SapBERT, xMEN -> مراجع الطرق biomedical
```

الفرق المهم:

```text
الـrepository أوpaper أعطتنا تعريف أوimplementation الطريقة.
أرقام accuracy جاءت من تشغيلنا المحلي على Egyptian catalog والـ464 pairs.
```

إذن العبارة الصحيحة هي: "استخدمنا method من هذا المصدر وحصلنا محليا على هذه النتيجة." لا نقول إن المصدر الأصلي حقق نفس الرقم على البيانات المصرية.

كل الـadapters شغلت من `run_competitor_benchmark.py`، والنتائج محفوظة في `all_evaluated_method_scores.csv`.

---

## Slide 32: Ablation Contract and Top-Level Paths

### الشرح

**Ablation** معناها نشيل component واحدة، نعيد تشغيل كل الـ464 case، ثم نقارن بالنظام الكامل.

الـbaseline:

```text
Hit@1  = 50.431%
Hit@20 = 73.276%
```

مثال إزالة family rescue:

```text
Hit@1  -> 36.638%
Hit@20 -> 56.034%
```

الحالة `TUTORIALAE -> KETOROLAC` كانت rank 7، وبعد إزالة الـrescue خرجت من top 20. هذا أكبر dependency مقاسة.

إزالة full-name retriever خفضت Hit@20 إلى `72.414%`. إزالة context-clean pass لم تغير top-k على المجموعة الحالية لأن طرقا أخرى غطت الحالات.

**مهم:** الـdeltas لا تجمع حسابيا. نفس الحالة قد تعتمد على family rescue وdelete keys وweighted edit معا. كل row تجيب سؤالا واحدا: ماذا يحدث لو غاب هذا الجزء فقط؟

---

## Slide 33: Retrieval Ablations With Measured Losses

### الشرح

هنا نفصل family rescue إلى أجزاء أصغر:

```text
بدون short-edge retrieval      Hit@20 = 70.259%
بدون family-head rescue        Hit@20 = 70.905%
بدون delete-key retrieval      Hit@20 = 71.121%
بدون compatible-length scan    Hit@20 = 71.767%
بدون short visible-head        Hit@20 = 73.060%
```

أمثلة توضح وظيفة كل جزء:

```text
RICOHIL -> RIVOTRIL  تحتاج short-edge evidence
LANYU   -> LANTUS    تحتاج head وdelete overlap
INDULGENCE -> INDERAL تحتاج compatible-length scan
LANS    -> LANTUS    تحتاج short visible-head rescue
```

Short-frame rescue كان net delta صفر، لكنه خسر حالة وكسب حالة. لذلك الصفر لا يعني أن النتائج نفسها لم تتغير.

**الخلاصة:** retrieval ablation تقول هل target وصلت candidate pool أصلا، وليس فقط هل ترتيبها تغير.

---

## Slide 34: Retrieval Ablations With Zero Net Change

### الشرح

**Zero net change** معناها عدد النجاحات النهائي لم يتغير. لا تعني أن component لم تعمل.

قد يحدث أحد أمرين:

```text
Path أخرى عوضت الـcomponent المحذوفة.
أو gain وloss حدثا معا فألغى كل منهما الآخر.
```

مثال multi-step chains: إزالتها لم تغير OCR top-k، لأن حالات مثل `uraranx -> ORAMAX` وصلت من evidence أخرى. لكن على `66,257` synthetic pair، الإزالة خسرت 343 Hit@1 case وكسبت 3 فقط.

نفس zero OCR delta ظهرت في عدة branches مثل keyboard rescue وligature rescue وبعض multi-step variants.

**القرار الصحيح:** لا نحذف component اعتمادا على صف OCR واحد. نحتاج group ablation، synthetic check، holdout جديد، وقياس runtime أوmaintenance قبل الحذف.

---

## Slide 35: Scoring Signals With the Largest Effects

### الشرح

الـretrieval تدخل family إلى الـpool. الـscoring تحدد هل تبقى داخل top 20 وأين تظهر.

أكبر الخسائر عند إزالة features:

```text
بدون weighted edit   Hit@20 = 66.164%  delta -7.112 points
بدون raw edit        Hit@20 = 67.888%
بدون length coverage Hit@20 = 70.259%
بدون position        Hit@20 = 71.336%
بدون prefix          Hit@20 = 71.336%
بدون n-grams         Hit@1  = 48.060%, Hit@20 = 71.983%
```

أمثلة:

```text
TUTORIALAE -> KETOROLAC خرجت بدون weighted edit.
TEFAXATE -> TELFAST خرجت بدون positional evidence.
RIVITAM -> RIVOTRIL خرجت بدون prefix evidence.
```

**الاستنتاج:** edit هي أقوى إشارة عامة، لكن الطول والموقع والقطع المحلية تمنعها من اختيار اسم قريب بطريقة غير منطقية.

---

## Slide 36: Scoring Signals With Smaller or Rank-Only Effects

### الشرح

بعض features تأثيرها أقل، لكنه ما زال واضحا على حالات محددة.

```text
بدون confusion costs  Hit@1 = 48.707%, Hit@20 = 72.845%
بدون skeleton         خسارة top-20 case واحدة
بدون subsequence      خسارتان وgain واحدة
```

أمثلة rank-only:

```text
بدون phonetic evidence:
ECOFIXIM -> CEFIXIME من rank 1 إلى 2

بدون agreement bonus:
OSSETIA -> OSSICA من rank 1 إلى 3

بدون suffix evidence:
RIVOFLURAL -> RIVOTRIL من rank 1 إلى 2
```

Hit@20 لا ترى هذه التغييرات لأن target ما زالت موجودة في القائمة. Hit@1 تكشف أن أول اختيار أصبح أسوأ.

**الخلاصة:** feature قد تكون مهمة للترتيب حتى لو لم تغير retrieval coverage.

---

## Slide 37: Reranker Ablations

### الشرح

عند إزالة كل deterministic reranking:

```text
Hit@1  هبطت من 50.431% إلى 40.517%
Hit@20 هبطت إلى 70.690%
```

عند إزالة candidate-pool وfamily-head rerankers فقط:

```text
Hit@1  = 48.276%
Hit@20 = 71.336%
```

`LANYU -> LANTUS` كانت rank 2 ثم خرجت من القائمة.

إزالة character-evidence rerankers خفضت Hit@1 إلى `48.922%` من غير Hit@20 loss. `RIVOFN2 -> RIVOTRIL` انتقلت من rank 1 إلى 2.

إزالة strict full-name correction خفضت Hit@1 إلى `49.569%`. `MYOLANA -> MYOLAX` أصبحت rank 2.

**الخلاصة:** الـreranker لا تضيف confidence. هي تصلح ترتيب حالات محددة بعد أن تكون candidate وصلت بالفعل.

---

## Slide 38: Score Tuning, Safety, and Atomic Flags

### الشرح

الـatomic flag هي switch صغيرة تشغل أوتقفل branch واحدة داخل component أكبر. اختبرنا 54 flag منفردة.

إزالة safety clarification gate لم تغير ranks. هذا متوقع لأنها تغير رسالة النظام، وليس ترتيب الأسماء.

وهنا يظهر نقص Hit@k: لو top 20 نفسها لم تتغير، لكن الرد أصبح "هذا الدواء مؤكد" بدلا من "قارن وتأكد"، Hit@1 وHit@20 لن تكتشفا الخطر. لذلك نحتاج safety metric مستقلة.

إغلاق strict full-name evidence guard زاد Hit@1 ظاهريا إلى `50.647%`، لكنه سبب gainين وloss واحدة. الزيادة الصافية وحدها لا تثبت أن التغيير أفضل.

إغلاق strict full-name rerank سبب 4 H@1 losses ووصلت النتيجة إلى `49.569%`.

بقية الـflags لم تغير aggregate top-k منفردة. التغييرات التفصيلية محفوظة في `algorithm_6_replay_metrics.csv`.

---

## Slide 39: Algorithm 6 Consensus-Source Ablations

### الشرح

السلايد تعزل الجزء الجديد في Algorithm 6.

عند إزالة rank-20 slot:

```text
Hit@20 هبطت من 73.276% إلى 72.845%
```

الحالتان المفقودتان:

```text
TEFA       -> TELFAST
LACTULOSE  -> LACTO
```

`TEFA` تحتاج votes من Jaro وtoken-sort وDice. حذف أي واحدة منها يجعل عدد المصادر أقل من 3.

`LACTO` تحتاج BM25+ لكي تحتفظ بالدعم الكافي لدخول rank 20.

إزالة Match Rating أوWRatio أوNYSIIS أوSymSpell أوSoundex منفردة لم تغير الحالتين، لأن مصادر أخرى عوضتها.

**الخلاصة الرقمية:** حالتان Hit@20 إضافيتان، صفر Hit@1 changes، صفر synthetic changes، مقابل `19.96 ms` overhead.

---

## Slide 40: Failures From Missing or Insufficient Evidence

### الشرح

من أصل 464 case، توجد 124 top-20 miss. في 97 منها، target لم تظهر في أي واحدة من العشر قوائم.

هذه الحالات لا يحلها reranking، لأن الاسم الصحيح غير موجود أصلا في الـunion.

أمثلة:

```text
H -> RIVO
حرف واحد، صفر source support، والرد no_match. هذا أكثر أمانا من التخمين.

HOAVACH -> AMIKACIN
المسافة 6 edits وصفر source support. معظم evidence اختفت.

LANSOPRAZOLE -> LANTUS
LANTUS ظهرت في source واحدة فقط، بينما PANTOPRAZOLE أقرب للنص.

RIV -> RIVOTRIL
RIVOTRIL ظهرت في مصدرين، لكن RIVO family حقيقية وتفسر النص بالكامل.
```

**الحل يختلف حسب السبب:** OCR أفضل، representation جديدة، معلومة unreadable position، أو مراجعة label. تغيير sorting وحده لن يكفي.

---

## Slide 41: Failures From Gate Rejection or Label Conflict

### الشرح

الـ27 miss الباقية فيها بعض support، لكن candidate فشلت gate أوالنص يشير بقوة إلى دواء آخر.

أمثلة gate rejection:

```text
OSCAR -> OSTOCAL
مصدران فقط وJaro .832، لذلك تفشل شروط 3 sources و.85 Jaro.

NEUROTROPHIC -> NEUROCET
4 sources وJaro .850، لكن Levenshtein .417 أقل من .55.
```

أمثلة label conflict:

```text
LANLTA -> LANTUS
LANETAL أقرب للنص بمسافة edit واحدة.

TOCILIZUMAB -> TOCO
TOCO تتجاهل معظم الحروف الظاهرة.

CINNARIZIN -> MYOLAX
CINNARIZINE اسم حقيقي على بعد edit واحدة، بينما MYOLAX على بعد 9.
```

**الخلاصة:** لا نخفض thresholds لمجرد إرضاء label. أولا نراجع الصورة ونتأكد أن target منطقية، لأن تحسين label خاطئة قد يقلل أمان التطبيق.

---

## Slide 42: Runtime and Query-Time Work

### الشرح

هناك نوعان من الوقت:

1. **Startup:** بناء indexes والـmatrices والphonetic arrays وSymSpell للـ`17,476` family. يحدث مرة عند تشغيل الـprocess. لا يوجد قياس منفصل موثق له أو للـpeak memory حاليا.
2. **Query time:** الوقت بعد أن يصبح كل شيء جاهزا.

الأرقام المقاسة:

```text
Deterministic core mean = 28.54 ms/query
Algorithm 6 mean        = 48.50 ms/query
Consensus overhead      = 19.96 ms/query
```

`48.50 ms` تعني `.0485` ثانية، أو نحو `20.6` query في الثانية نظريا في process واحدة تعمل بالتتابع. الـcore وحدها تعادل نحو `35.0` query في الثانية.

هذه warm single-process means. لا تشمل network أوbrowser، ولا تمثل P95 أوconcurrent production load.

**التحسين المنطقي لاحقا:** cache للتحضير وتشغيل المصادر المستقلة بالتوازي، مع اختبار أن top 20 لم تتغير.

---

## Slide 43: Executable Algorithm Summary

### الشرح

دي الرحلة كلها كتعليمات تنفيذ:

```text
Input:
نص الاسم + مكان أي جزء غير مقروء

1. Normalize النص واعمل compact form.
2. احذف dose وform في نسخة إضافية عند الحاجة.
3. ابحث بالاسم الكامل.
4. اجمع candidates من prefix وsuffix وn-grams وskeleton وphonetic وdeletion وfamily heads.
5. ولد typo variants عامة ومحدودة.
6. احسب score لكل family من 12 feature.
7. ادمج ظهور نفس family من كل path.
8. طبق reranking محدودة عند وجود advantage واضحة.
9. شغل التسع طرق المستقلة.
10. اجمع source count وRRF وsimilarities.
11. اسمح بإنقاذ family واحدة في rank 20 إذا حققت 3 sources و.55 Levenshtein و.85 Jaro.

Output:
حتى 20 family مع reasons وvariants، أو no_match.
```

الـcalibrator مقفولة، لذلك لا يوجد probability claim نشط. كل نتيجة تحتاج confirmation.

---

## Slide 44: Algorithm 6 in One Sentence

### الشرح

**الجملة المختصرة:** Algorithm 6 تحول النص المشوه إلى عدة أدلة، تستخدمها لجلب medicine families وترتيبها، ثم تسمح بإنقاذ family واحدة في نهاية top 20 عندما تتفق ثلاث طرق مستقلة ويظل التشابه الحرفي قويا، من غير أن تحول هذا الاتفاق إلى تأكيد طبي.

**مثال سريع:**

```text
TEFA -> TELFAST
```

الـcore لم تجدها في top 20، لكن ثلاث طرق وجدتها ونجحت في gates، فظهرت rank 20 للمقارنة.

**النتيجة:**

```text
OCR fair unique pairs = 464
Hit@1                 = 50.43%
Hit@20                = 73.28%
Core latency          = 28.54 ms
A6 latency            = 48.50 ms
Consensus gain        = حالتان Hit@20 بلا paired loss
```

**الرسالة النهائية:** الناتج possibilities تحتاج confirmation، وليس prescription decision.
