"""Human-friendly training groups and transparent exercise-focus classifications."""

BODY_PARTS = {
    "abdominals": "Abs",
    "upper abs": "Abs",
    "lower abs": "Abs",
    "obliques": "Abs",
    "chest": "Chest",
    "upper chest": "Chest",
    "lower chest": "Chest",
    "quadriceps": "Quads",
    "hamstrings": "Hamstrings",
    "adductors": "Adductors",
    "abductors": "Abductors",
    "lats": "Back",
    "middle back": "Back",
    "lower back": "Back",
    "traps": "Back",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "forearms": "Forearms",
    "shoulders": "Shoulders",
    "calves": "Calves",
    "glutes": "Glutes",
    "neck": "Neck",
}
MUSCLE_LABELS = {
    "abdominals": "Abs",
    "quadriceps": "Quads",
    "hamstrings": "Hamstrings",
    "adductors": "Adductors",
    "abductors": "Abductors",
    "middle back": "Mid back",
    "lower back": "Lower back",
    "lats": "Lats",
    "traps": "Traps",
}
REVERSE_CURL_IDS = {
    "Reverse_Barbell_Curl",
    "Reverse_Barbell_Preacher_Curls",
    "Reverse_Cable_Curl",
    "Reverse_Plate_Curls",
    "Standing_Dumbbell_Reverse_Curl",
}
# Reviewed assisting groups absent from the pinned upstream records. These are
# movement classifications, not measurements of activation or extra primary sets.
SECONDARY_MUSCLE_ADDITIONS = {
    "Butterfly": ["shoulders"],
    "Hammer_Curls": ["forearms"],
    "Cable_Hammer_Curls_-_Rope_Attachment": ["forearms"],
    "Standing_Biceps_Cable_Curl": ["forearms"],
    "Seated_Dumbbell_Curl": ["forearms"],
    "Cable_Rear_Delt_Fly": ["middle back", "traps"],
}


def body_part(muscle):
    muscle = muscle.casefold().replace("_", " ")
    return BODY_PARTS.get(muscle, muscle.title())


def classify(exercise):
    result = dict(exercise)
    result["secondaryMuscles"] = list(
        dict.fromkeys(
            exercise["secondaryMuscles"] + SECONDARY_MUSCLE_ADDITIONS.get(exercise["id"], [])
        )
    )
    if exercise["id"] in REVERSE_CURL_IDS:
        result["primaryMuscles"] = ["forearms"]
        result["secondaryMuscles"] = list(
            dict.fromkeys(["biceps"] + [m for m in result["secondaryMuscles"] if m != "forearms"])
        )
    result["bodyParts"] = sorted({body_part(m) for m in result["primaryMuscles"]})
    return result


def training_areas(exercise, group):
    """Describe recorded movement emphasis, rather than claim isolated activation."""
    name = exercise["name"].casefold()
    if group == "Chest":
        if "incline" in name:
            return ["Incline movements"]
        if "decline" in name:
            return ["Decline movements"]
        return ["Flat / general chest"]
    if group == "Abs":
        if any(word in name for word in ("plank", "hold", "hollow")):
            return ["Holds / stability"]
        if any(word in name for word in ("twist", "side", "oblique")):
            return ["Side / rotation"]
        if any(word in name for word in ("leg raise", "knee raise", "reverse crunch", "hip raise")):
            return ["Leg / knee raises & reverse crunches"]
        return ["Crunches / general abs"]
    if group == "Forearms":
        if exercise["id"] in REVERSE_CURL_IDS:
            return ["Reverse curls"]
        if "wrist" in name:
            return ["Wrist work"]
        return ["Grip / other forearm work"]
    return sorted(
        {
            MUSCLE_LABELS.get(m, m.title())
            for m in exercise["primaryMuscles"]
            if body_part(m) == group
        }
    )
