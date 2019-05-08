defmodule RisteysWeb.PhenocodeController do
  use RisteysWeb, :controller
  alias Risteys.{Repo, Icd9, Icd10, Phenocode, PhenocodeIcd10, PhenocodeIcd9, StatsSex}
  import Ecto.Query
  import Phoenix.HTML

  def show(conn, %{"name" => name}) do
    phenocode = Repo.get_by(Phenocode, name: name)

    # Get the descriptions, if any.
    no_desc = ["No definition available."]

    {descriptions, ontology} =
      if not is_nil(phenocode.ontology) do
        Map.pop(phenocode.ontology, "DESCRIPTION", no_desc)
      else
        {no_desc, %{}}
      end

    stats = get_stats(phenocode)

    conn
    |> assign(:name, phenocode.name)
    |> assign(:title, phenocode.longname)
    |> assign(:data_sources, data_sources(phenocode))
    |> assign(:ontology, ontology)
    |> assign(:stats, stats)
    |> assign(:distrib_year, phenocode.distrib_year)
    |> assign(:distrib_age, phenocode.distrib_age)
    |> assign(:descriptions, descriptions)
    |> render("show.html")
  end

  defp data_sources(phenocode) do
    icd10s =
      Repo.all(
        from assoc in PhenocodeIcd10,
          join: p in Phenocode,
          on: assoc.phenocode_id == p.id,
          join: icd in Icd10,
          on: assoc.icd10_id == icd.id,
          where: p.id == ^phenocode.id,
          select: %{registry: assoc.registry, icd: icd}
      )

    hd_icd10s = filter_icds_registry(icd10s, "HD")
    cod_icd10s = filter_icds_registry(icd10s, "COD")
    kela_icd10s = filter_icds_registry(icd10s, "KELA_REIMB")

    icd9s =
      Repo.all(
        from assoc in PhenocodeIcd9,
          join: p in Phenocode,
          on: assoc.phenocode_id == p.id,
          join: icd in Icd9,
          on: assoc.icd9_id == icd.id,
          where: p.id == ^phenocode.id,
          select: %{registry: assoc.registry, icd: icd}
      )

    hd_icd9s = filter_icds_registry(icd9s, "HD")
    cod_icd9s = filter_icds_registry(icd9s, "COD")

    %{
      hd_icd10s: hd_icd10s,
      cod_icd10s: cod_icd10s,
      kela_icd10s: kela_icd10s,
      hd_icd9s: hd_icd9s,
      cod_icd9s: cod_icd9s,
      hd_icd8s: phenocode.hd_icd_8,
      cod_icd8s: phenocode.cod_icd_8,
      outpat_icd: phenocode.outpat_icd,
      oper_nom: phenocode.oper_nom,
      oper_hl: phenocode.oper_hl,
      oper_hp1: phenocode.oper_hp1,
      oper_hp2: phenocode.oper_hp2,
      kela_reimb: phenocode.kela_reimb,
      kela_atc_needother: phenocode.kela_atc_needother,
      kela_atc: phenocode.kela_atc,
      canc_topo: phenocode.canc_topo,
      canc_morph: phenocode.canc_morph,
      omit: phenocode.omit,
      sex: phenocode.sex,
      conditions: phenocode.conditions
    }
  end

  defp filter_icds_registry(icds, wanted_registry) do
    Enum.reduce(icds, [], fn %{registry: registry, icd: icd}, acc ->
      if registry == wanted_registry do
        acc ++ [icd]
      else
        acc
      end
    end)
  end

  defp get_stats(phenocode) do
    stats = Repo.all(from ss in StatsSex, where: ss.phenocode_id == ^phenocode.id)

    [stats_all] = Enum.filter(stats, fn stats_sex -> stats_sex.sex == 0 end)
    [stats_female] = Enum.filter(stats, fn stats_sex -> stats_sex.sex == 2 end)
    [stats_male] = Enum.filter(stats, fn stats_sex -> stats_sex.sex == 1 end)

    %{
      all: stats_all,
      female: stats_female,
      male: stats_male
    }
  end

  defp plots_data(phenocode_name) do
    bin_by_age = Risteys.Data.bin_by_age(phenocode_name)

    bin_by_age =
      for {[mini, maxi], count} <- bin_by_age do
        bracket = "#{mini}–#{maxi}"
        {bracket, count}
      end

    %{
      events_by_year: Risteys.Data.count_by_year(phenocode_name),
      bin_by_age: bin_by_age
    }
  end
end