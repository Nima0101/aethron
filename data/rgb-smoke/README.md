# RGB integration smoke images (not evaluation accuracy)
Two fixed sample photographs were chosen before model inference to exercise positive class decoding, alongside empty/dark and small-aircraft negatives. Expected classes: person and animal. A failure is retained, not replaced with a more convenient image. No localization metric or field-generalization claim: these common images may overlap upstream model training. Repeated frames later used in a demo are synthetic time repetition of a still, not a video recording. No identity inference is performed.

- person.png: unmodified NASA public-domain astronaut photograph, distributed by [scikit-image v0.25.2](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/astronaut.png); [documentation identifies its NASA/public-domain origin](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut). No endorsement implied.
- animal.png: unmodified cat photograph by Stefan van der Walt, CC0, distributed by [scikit-image v0.25.2](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/chelsea.png); [documented CC0 terms](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.chelsea).

These image rights are separate from AETHRON's Apache2 code. Keep attribution with any derived overlay. No third-party Visage image is included.
