from streamlit.testing.v1 import AppTest
from researchbridge.core import ROOT


def launch():
    return AppTest.from_file(ROOT / "app.py", default_timeout=45).run()


def test_app_boots_with_real_data():
    app = launch()
    assert not app.exception
    assert [m.value for m in app.metric] == ["60", "56", "79", "135"]
    assert len(app.tabs) == 7


def test_search_no_results_and_example_recovery():
    app = launch()
    app.text_input(key="search_query").set_value("zzxq987654xyz")
    next(b for b in app.button if b.label == "搜尋文獻").click().run()
    assert not app.exception
    assert any("沒有符合" in x.value for x in app.info)
    app.button(key="keyword_method_llm").click().run()
    assert not app.exception
    assert app.text_input(key="search_query").value == "大型語言模型與聊天機器人"
    assert any("EMPATHICA" in x.value for x in app.markdown)


def test_comparison_persists_across_searches():
    app = launch()
    app.button(key="save_41726533").click().run()
    assert not app.exception
    assert "41726533" in app.session_state["comparison"]
    app.button(key="keyword_method_cohort").click().run()
    assert not app.exception
    assert "41726533" in app.session_state["comparison"]
    assert any("EMPATHICA" in x.value for x in app.markdown)


def test_language_theme_and_threshold_preserve_selections():
    app = launch()
    app.button(key="save_41726533").click().run()
    app.selectbox(key="language").set_value("es").run()
    assert not app.exception
    assert app.tabs[0].label == "Explorar artículos"
    assert app.text_input(key="search_query").value == "alfabetización sobre medicamentos"
    assert "41726533" in app.session_state["comparison"]
    app.selectbox(key="theme_es").set_value("dark").run()
    assert not app.exception
    app.number_input(key="score_min").set_value(0.99).run()
    assert tuple(app.slider(key="score_range").value) == (0.99,1.0)
    assert not [b for b in app.button if b.key and b.key.startswith("save_")]
    assert [b for b in app.button if b.key and b.key.startswith("bridge_save_")]
    assert "41726533" in app.session_state["comparison"]
    app.number_input(key="score_max").set_value(0.2).run()
    assert app.error and not app.exception
    assert [b for b in app.button if b.key and b.key.startswith("bridge_save_")]
    app.slider(key="score_range").set_value((0.0,0.6)).run()
    assert app.number_input(key="score_min").value == 0
    assert app.number_input(key="score_max").value == 0.6
    app.selectbox(key="language").set_value("en").run()
    assert app.tabs[1].label == "Methods & Bridges" and not app.exception
    assert tuple(app.slider(key="score_range").value) == (0.0,0.6)


def test_bridge_selection_changes_papers_and_saves():
    app = launch()
    app.selectbox(key="method_choice_zh").set_value("llm").run()
    app.selectbox(key="bridge_choice_zh").set_value("privacy").run()
    assert not app.exception
    assert any(b.key == "bridge_save_40963721" for b in app.button)
    app.button(key="bridge_save_40963721").click().run()
    assert "40963721" in app.session_state["comparison"]
    app.selectbox(key="bridge_choice_zh").set_value("medication").run()
    assert not any(b.key == "bridge_save_40963721" for b in app.button)
    app.selectbox(key="language").set_value("en").run()
    assert app.selectbox(key="method_choice_en").value == "llm"
    assert app.selectbox(key="bridge_choice_en").value == "medication"
    assert "40963721" in app.session_state["comparison"]


def test_source_checker_and_brief_are_functional():
    from researchbridge.core import load_data
    app = launch()
    paper = next(p for p in load_data()[0] if p["pmid"] == "41726533")
    app.multiselect(key="check_ids").set_value([paper["pmid"]])
    app.text_area(key="claims").set_value(paper["sections"][0]["text"]+"\nA fabricated claim without a source.")
    app.button(key="check_button").click().run()
    assert not app.exception
    assert any("直接文字匹配" in x.value for x in app.success)
    assert any("需要人工確認" in x.value for x in app.warning)
    assert any("# 研究機會簡報" in x.value and paper["pmid"] in x.value for x in app.markdown)


def test_custom_query_is_preserved_but_default_is_localized():
    app = launch()
    app.selectbox(key="language").set_value("en").run()
    assert app.text_input(key="search_query").value == "medication literacy"
    app.text_input(key="search_query").set_value("privacy protein custom")
    next(b for b in app.button if b.label=="Search papers").click().run()
    app.selectbox(key="language").set_value("es").run()
    assert app.text_input(key="search_query").value == "privacy protein custom"
    assert "Por ejemplo" in app.text_input(key="search_query").placeholder

def test_comparison_contains_profiles_pairs_and_export_choices():
    app = launch()
    app.multiselect(key="comparison").set_value(["41726533","41726516"]).run()
    assert not app.exception
    assert any(m.label=="論文關聯分數（cosine）" for m in app.metric)
    assert any("共同點" in x.value for x in app.markdown)
    assert app.selectbox(key="comparison_format").options == ["CSV","PDF","HTML"]
    app.selectbox(key="comparison_format").set_value("pdf").run()
    assert not app.exception
    app.selectbox(key="comparison_format").set_value("html").run()
    assert not app.exception

def active_tab_index(app):
    return next(node.proto.tab_container.default_tab_index for node in app.main if getattr(node,"proto",None) is not None and hasattr(node.proto,"tab_container") and node.proto.HasField("tab_container"))


def test_language_and_theme_keep_current_page_and_comparison():
    app = launch()
    app.multiselect(key="comparison").set_value(["41726533","41726516"]).run()
    app.session_state["active_tab"] = "tab_compare"
    app.run()
    assert active_tab_index(app)==2
    for language,label in (("en","Compare papers"),("es","Comparar artículos"),("zh","研究比較")):
        app.selectbox(key="language").set_value(language).run()
        assert not app.exception
        assert active_tab_index(app)==2
        assert app.session_state["navigation_tabs"]==label
        assert app.session_state["comparison"]==["41726533","41726516"]
    app.selectbox(key="theme_zh").set_value("dark").run()
    assert not app.exception and active_tab_index(app)==2


def test_bridge_page_and_choices_survive_language_change():
    app = launch()
    app.session_state["active_tab"]="tab_bridges"
    app.run()
    app.selectbox(key="method_choice_zh").set_value("llm").run()
    app.selectbox(key="bridge_choice_zh").set_value("privacy").run()
    app.selectbox(key="language").set_value("en").run()
    assert not app.exception and active_tab_index(app)==1
    assert app.selectbox(key="method_choice_en").value=="llm"
    assert app.selectbox(key="bridge_choice_en").value=="privacy"

def test_legacy_privacy_query_translates_through_all_languages_without_resetting_page():
    app=AppTest.from_file(ROOT / "app.py",default_timeout=45)
    app.query_params["q"]="大型語言模型 隱私"
    app.run()
    app.session_state["active_tab"]="tab_bridges"
    app.run()
    for language,query in (("en","large language models privacy"),("es","modelos de lenguaje privacidad"),("zh","大型語言模型 隱私")):
        app.selectbox(key="language").set_value(language).run()
        assert not app.exception
        assert app.text_input(key="search_query").value==query
        assert app.query_params["q"]==query
        assert active_tab_index(app)==1


def test_recommended_keyword_query_follows_interface_language():
    app=launch()
    app.button(key="keyword_method_llm").click().run()
    assert app.text_input(key="search_query").value=="大型語言模型與聊天機器人"
    app.selectbox(key="language").set_value("en").run()
    assert not app.exception
    assert app.text_input(key="search_query").value=="LLMs and chatbots"
    app.selectbox(key="language").set_value("es").run()
    assert not app.exception
    assert app.text_input(key="search_query").value=="Modelos de lenguaje y chatbots"
    assert any("EMPATHICA" in x.value for x in app.markdown)


def test_bridge_search_updates_shared_goal_and_recommendations_without_leaving_page():
    app=launch()
    app.session_state["active_tab"]="tab_bridges"
    app.run()
    assert app.text_input(key="bridge_search_query").value==app.text_input(key="search_query").value
    app.text_input(key="bridge_search_query").set_value("蛋白質")
    app.button(key="bridge_search_submit").click().run()
    assert not app.exception and active_tab_index(app)==1
    assert app.text_input(key="search_query").value=="蛋白質"
    assert app.query_params["q"]=="蛋白質"
    assert any(b.key=="explore_protein" for b in app.button)
    assert any(b.key=="bridge_save_41049045" for b in app.button)
    app.text_input(key="search_query").set_value("custom privacy goal")
    app.button(key="search_submit").click().run()
    assert not app.exception
    assert app.text_input(key="bridge_search_query").value=="custom privacy goal"
    app.selectbox(key="language").set_value("es").run()
    assert app.text_input(key="bridge_search_query").value=="custom privacy goal"
    assert active_tab_index(app)==1


def test_bridge_search_follows_keyword_and_language_changes():
    app=launch()
    app.button(key="keyword_method_llm").click().run()
    for language,query in (("en","LLMs and chatbots"),("es","Modelos de lenguaje y chatbots"),("zh","大型語言模型與聊天機器人")):
        app.selectbox(key="language").set_value(language).run()
        assert not app.exception
        assert app.text_input(key="search_query").value==query
        assert app.text_input(key="bridge_search_query").value==query


def test_bridges_show_three_pair_scores_for_three_visible_papers():
    app=launch()
    app.session_state["active_tab"]="tab_bridges"
    app.run()
    app.select_slider(key="limit").set_value(3).run()
    assert not app.exception
    assert any("Bridges 結果彼此的相關性" in x.value for x in app.markdown)
    assert any("3／6" in x.value and "3 組" in x.value for x in app.caption)
    assert not any("不套用左側門檻" in x.value for x in app.caption)
    app.number_input(key="score_min").set_value(0.99).run()
    assert any("3／6" in x.value and "3 組" in x.value for x in app.caption)
    app.selectbox(key="bridge_choice_zh").set_value("care").run()
    assert not app.exception
    assert any("至少需要兩篇" in x.value for x in app.info)
    app.selectbox(key="language").set_value("en").run()
    assert not app.exception and active_tab_index(app)==1
    assert any("At least two" in x.value for x in app.info)
    assert not any("search threshold does not apply" in x.value for x in app.caption)
