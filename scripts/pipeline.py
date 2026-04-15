import scripts.detection_concepts as detection_concepts
import scripts.ontology_concepts as ontology_concepts
import scripts.NLP_explainer as NLP_explainer

from owlready2 import *

# Dynamically get path to project root (assumes src is inside the root)
this_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(this_dir, ".."))
pr2_imagepth = os.path.join(project_root, "models", "images", "pr2_speaking.png")
# Build the absolute path to the ontology
ontology_path = os.path.join(project_root, "models", "ontologies", "meals.owl")
onto = get_ontology(ontology_path).load()


SOMA = onto.get_namespace("http://www.ease-crc.org/ont/SOMA.owl#")
CUT2 = onto.get_namespace("http://www.ease-crc.org/ont/situation_awareness#")
CUT = onto.get_namespace("http://www.ease-crc.org/ont/food_cutting#")
DUL = onto.get_namespace("http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#")
OBO = onto.get_namespace("http://purl.obolibrary.org/obo/")
MEALS = onto.get_namespace("http://www.ease-crc.org/ont/meals#")
with onto:
    owlready2.sync_reasoner_pellet()

leaf_classes = ontology_concepts.get_all_leaf_subclasses(MEALS.Food)

def get_prompts():
    return ontology_concepts.convert_leaf_subclasses(leaf_classes)


def get_bboxes(img_path):
   return detection_concepts.detect_objects("food.", img_path, threshold = 0.4)


def get_detection_results(img_path, prompts):
    # Create a list of food_concepts
    food_concepts = [ontology_concepts.get_food_concept(leaf_class) for leaf_class in leaf_classes]

    # Create a dictionary to map class labels to food concepts with the 'obo.' prefix
    food_concept_dict = {f"{food.namespace}": food for food in food_concepts}

    # Update the detection results with the corresponding food concepts
    detection_results = []
    for i in get_bboxes(img_path):
        for b in i["boxes"]:
            classified_class, classified_class_label = detection_concepts.run_clip_on_bboxes(img_path, bbox=b,
                                                                                             prompts=prompts,
                                                                                             show_results=False)
            if "obo." in classified_class:
                classified_class = str(classified_class).replace("obo.", "")
                classified_instance = OBO[classified_class](classified_class_label)

            if "SOMA." in classified_class:
                classified_class = str(classified_class).replace("SOMA.", "")
                classified_instance = SOMA[classified_class](classified_class_label)


            detection_result = detection_concepts.ObjectDetectionResult(
                bounding_box=b,
                predicted_class=classified_class,
                predicted_label=classified_class_label,
                ontology_instance=classified_instance
            )

            # Add the corresponding food concept to the detection result
            if f"obo.{classified_class}" in food_concept_dict:
                detection_result.ontology_concept = food_concept_dict[f"obo.{classified_class}"]
                detection_result.add_semantic_annotations(OBO)
            if f"SOMA.{classified_class}" in food_concept_dict:
                detection_result.ontology_concept = food_concept_dict[f"SOMA.{classified_class}"]
                detection_result.add_semantic_annotations(SOMA)
            # else:
            # print(f"Classified class {classified_class} not found in food_concept_dict")

            # detection_result.add_semantic_annotations(OBO)
            detection_results.append(detection_result)

    return detection_results

#
def get_clicked_obj(img_path, x, y):
    detection_results = get_detection_results(img_path, get_prompts())
    #clicked_coords = detection_concepts.show_click_coordinates(img_path)
    clicked_coords = (x,y)
    clicked_obj = []
    for i in detection_results:
        x1, y1, x2, y2 = i.bounding_box.tolist()
        #for coord in clicked_coords:
        x, y = clicked_coords
        if x1 < x < x2 and y1 < y < y2:
            print(
                    f"Coordinate {clicked_coords} is inside the bounding box {i.bounding_box}: (label: {i.ontology_concept.name})")
            clicked_obj.append(i.ontology_concept)

    if not clicked_obj:
        print("No object clicked or no object detected in the image.")

    if len(clicked_obj) > 1:
        raise ValueError("Multiple objects detected at the clicked coordinates. Please ensure only one object is clicked.")


    return clicked_obj


def provide_explanation(clicked_obj, llm_model=None):
    if isinstance(clicked_obj[0], str):
        content = clicked_obj[0]
    else:
        content = clicked_obj[0]
    
    try:
        explanation = NLP_explainer.generate_explanation(content, llm_model=llm_model)
    except Exception as e:
        print(f"Error generating AI explanation: {e}")
        # Use the name of the object if possible
        label = content.name if hasattr(content, 'name') else str(content)
        explanation = generate_fallback_explanation(label)

    return explanation

def generate_explanation_for_label(label, llm_model=None):
    # This is a bit of a hack to work with the name/label.
    # In a real scenario we'd pass the actual concept.
    # But for now, we'll just explain based on label.
    try:
        explanation = NLP_explainer.generate_explanation(label, llm_model=llm_model)
    except Exception as e:
        print(f"Error generating AI explanation: {e}")
        # Hardcoded fallback
        explanation = generate_fallback_explanation(label)
    return explanation

def generate_fallback_explanation(label):
    # Find the concept for the label to get attributes
    concept = None
    for leaf in leaf_classes:
        # Check if the label matches the class name or the label
        # leaf.name often contains "FOODON_..." or "SOMA_..." but sometimes it's clean.
        # Let's check both the full name and the part after the underscore.
        leaf_name = leaf.name.split("/")[-1]
        
        # If label is "Apple" and leaf.label is "Apple", it should match.
        # leaf.label is a list of locstr.
        leaf_label_strs = [str(l) for l in leaf.label]
        
        if label.lower() == leaf_name.lower() or any(label.lower() == ls.lower() for ls in leaf_label_strs):
            concept = ontology_concepts.get_food_concept(leaf)
            break
    
    if not concept:
        return f"This is a {label}. I don't have much information about how to process it specifically, but we can try to cut it if needed."

    parts = []
    if concept.peel_must_be_removed or concept.peel_should_be_removed:
        parts.append("The peel has to be removed before cutting.")
    if concept.core_must_be_removed or concept.core_should_be_removed:
        parts.append("The core should be removed as well.")
    if concept.stem_must_be_removed or concept.stem_should_be_removed:
        parts.append("Don't forget to remove the stem.")
    
    if not parts:
        if concept.can_be_cut:
            return f"This {label} is ready to be cut and doesn't require any special preparation like peeling."
        else:
            return f"This is a {label}. It seems it's usually not something we cut in this way."

    return f"To prepare this {label}: " + " ".join(parts)

def get_boxes_only(img_path):
    results = get_bboxes(img_path)

    boxes = []
    for r in results:
        for b in r["boxes"]:
            boxes.append(b.tolist())

    return boxes